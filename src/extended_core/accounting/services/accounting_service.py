from __future__ import annotations
import datetime
from datetime import date
from decimal import Decimal
import uuid
from typing import List, Optional, Tuple

from src.extended_core.accounting.models import (
    Account,
    AccountType,
    AccountsPayable,
    AgingBucket,
    AgingItem,
    AgingReport,
    APStatus,
    IncomeStatement,
    JournalEntry,
    JournalLine,
    TrialBalance,
    TrialBalanceItem,
)
from src.shared.database import Database, default_db


class AccountingService:
    """Core accounting and general ledger engine for TanGii (Layer 2 Extended Core)."""

    def __init__(self, db: Database = default_db) -> None:
        self.db = db

    def create_journal_entry(
        self,
        entry_date: date,
        source_event: str,
        reference_id: str,
        description: str,
        lines: List[Tuple[str, Decimal, Decimal]],  # (account_code, debit, credit)
    ) -> JournalEntry:
        """Create a new double-entry journal entry with rigid balance validation."""
        if not lines:
            raise ValueError("傳票必須至少包含一筆借貸分錄")

        # Validate accounts and calculate debits/credits
        total_debit = Decimal("0.0")
        total_credit = Decimal("0.0")
        validated_lines = []

        with self.db.transaction() as conn:
            for account_code, debit, credit in lines:
                debit_dec = Decimal(str(debit))
                credit_dec = Decimal(str(credit))

                if debit_dec < Decimal("0.0") or credit_dec < Decimal("0.0"):
                    raise ValueError(f"科目 {account_code} 借貸金額不得為負數")
                if debit_dec == Decimal("0.0") and credit_dec == Decimal("0.0"):
                    raise ValueError(f"科目分錄之借方或貸方金額必須大於 0: {account_code}")

                # Ensure account exists
                acc = conn.execute(
                    "SELECT account_code, account_name FROM accounts WHERE account_code = ?",
                    (account_code,),
                ).fetchone()
                if not acc:
                    raise ValueError(f"會計科目代碼 {account_code} 不存在於會計科目表中 (does not exist)")

                total_debit += debit_dec
                total_credit += credit_dec
                validated_lines.append((account_code, debit_dec, credit_dec))

            # Rigid check of debit == credit
            if abs(total_debit - total_credit) > Decimal("0.001"):
                raise ValueError(
                    f"傳票借貸不平衡！借方總額 ({total_debit}) 不等於貸方總額 ({total_credit})，已禁止存檔 (Double-entry bookkeeping imbalance)"
                )

            entry_id = f"JE-{uuid.uuid4().hex[:10].upper()}"
            conn.execute(
                """
                INSERT INTO journal_entries (entry_id, entry_date, source_event, reference_id, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                (entry_id, entry_date.isoformat(), source_event, reference_id, description),
            )

            result_lines: List[JournalLine] = []
            for account_code, debit_dec, credit_dec in validated_lines:
                line_id = f"JL-{uuid.uuid4().hex[:10].upper()}"
                conn.execute(
                    """
                    INSERT INTO journal_lines (line_id, entry_id, account_code, debit, credit)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (line_id, entry_id, account_code, float(debit_dec), float(credit_dec)),
                )
                result_lines.append(
                    JournalLine(
                        line_id=line_id,
                        entry_id=entry_id,
                        account_code=account_code,
                        debit=debit_dec,
                        credit=credit_dec,
                    )
                )

        return JournalEntry(
            entry_id=entry_id,
            entry_date=entry_date,
            source_event=source_event,
            reference_id=reference_id,
            description=description,
            lines=result_lines,
        )

    def get_journal_entries(self, limit: int = 50) -> List[JournalEntry]:
        """Fetch journal entries ordered by date desc with their lines."""
        with self.db.transaction() as conn:
            entry_rows = conn.execute(
                """
                SELECT entry_id, entry_date, source_event, reference_id, description, created_at
                FROM journal_entries
                ORDER BY entry_date DESC, created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            entries: List[JournalEntry] = []
            for e_row in entry_rows:
                entry_id = e_row["entry_id"]
                line_rows = conn.execute(
                    """
                    SELECT line_id, entry_id, account_code, debit, credit
                    FROM journal_lines
                    WHERE entry_id = ?
                    ORDER BY debit DESC, credit ASC
                    """,
                    (entry_id,),
                ).fetchall()

                lines = [
                    JournalLine(
                        line_id=lr["line_id"],
                        entry_id=lr["entry_id"],
                        account_code=lr["account_code"],
                        debit=Decimal(str(lr["debit"])),
                        credit=Decimal(str(lr["credit"])),
                    )
                    for lr in line_rows
                ]

                # Parse date
                edate = (
                    datetime.date.fromisoformat(e_row["entry_date"])
                    if isinstance(e_row["entry_date"], str)
                    else e_row["entry_date"]
                )

                entries.append(
                    JournalEntry(
                        entry_id=entry_id,
                        entry_date=edate,
                        source_event=e_row["source_event"],
                        reference_id=e_row["reference_id"],
                        description=e_row["description"],
                        lines=lines,
                    )
                )

        return entries

    def get_trial_balance(self, as_of_date: Optional[date] = None) -> TrialBalance:
        """Compute cumulative Trial Balance across all accounts."""
        target_date = as_of_date or datetime.date.today()

        with self.db.transaction() as conn:
            # Query all accounts and their debit/credit aggregates up to target_date
            rows = conn.execute(
                """
                SELECT a.account_code, a.account_name, a.account_type,
                       COALESCE(SUM(sub.debit), 0) AS debit_total,
                       COALESCE(SUM(sub.credit), 0) AS credit_total
                FROM accounts a
                LEFT JOIN (
                    SELECT jl.account_code, jl.debit, jl.credit
                    FROM journal_lines jl
                    JOIN journal_entries je ON jl.entry_id = je.entry_id
                    WHERE je.entry_date <= ?
                ) sub ON a.account_code = sub.account_code
                WHERE a.is_active = 1
                GROUP BY a.account_code, a.account_name, a.account_type
                ORDER BY a.account_code ASC
                """,
                (target_date.isoformat(),),
            ).fetchall()

            items: List[TrialBalanceItem] = []
            total_balance_debit = Decimal("0.0")
            total_balance_credit = Decimal("0.0")

            for r in rows:
                acc_type = AccountType(r["account_type"])
                debit_sum = Decimal(str(r["debit_total"]))
                credit_sum = Decimal(str(r["credit_total"]))

                # Normal balance calculation
                if acc_type in (AccountType.ASSET, AccountType.EXPENSE):
                    # Normal Debit
                    if debit_sum >= credit_sum:
                        bal_debit = debit_sum - credit_sum
                        bal_credit = Decimal("0.0")
                    else:
                        bal_debit = Decimal("0.0")
                        bal_credit = credit_sum - debit_sum
                else:
                    # Normal Credit (LIABILITY, EQUITY, REVENUE)
                    if credit_sum >= debit_sum:
                        bal_debit = Decimal("0.0")
                        bal_credit = credit_sum - debit_sum
                    else:
                        bal_debit = debit_sum - credit_sum
                        bal_credit = Decimal("0.0")

                total_balance_debit += bal_debit
                total_balance_credit += bal_credit

                items.append(
                    TrialBalanceItem(
                        account_code=r["account_code"],
                        account_name=r["account_name"],
                        account_type=acc_type,
                        debit_total=debit_sum,
                        credit_total=credit_sum,
                        balance_debit=bal_debit,
                        balance_credit=bal_credit,
                    )
                )

        is_balanced = abs(total_balance_debit - total_balance_credit) < Decimal("0.01")

        return TrialBalance(
            as_of_date=target_date,
            items=items,
            total_debit=total_balance_debit,
            total_credit=total_balance_credit,
            is_balanced=is_balanced,
        )

    def get_income_statement(
        self, start_date: Optional[date] = None, end_date: Optional[date] = None
    ) -> IncomeStatement:
        """Compute multi-step Income Statement (Revenue - COGS = Gross Profit - Expenses = Net Profit)."""
        target_end_date = end_date or datetime.date.today()

        with self.db.transaction() as conn:
            date_filter = "je.entry_date <= ?"
            params = [target_end_date.isoformat()]
            if start_date:
                date_filter += " AND je.entry_date >= ?"
                params.append(start_date.isoformat())

            # Query aggregates for Revenue (4xxx), COGS (5xxx), and Expenses (6xxx)
            rows = conn.execute(
                f"""
                SELECT a.account_code, a.account_type,
                       COALESCE(SUM(jl.debit), 0) AS debit_sum,
                       COALESCE(SUM(jl.credit), 0) AS credit_sum
                FROM accounts a
                JOIN journal_lines jl ON a.account_code = jl.account_code
                JOIN journal_entries je ON jl.entry_id = je.entry_id
                WHERE {date_filter} AND a.account_type IN ('REVENUE', 'EXPENSE')
                GROUP BY a.account_code, a.account_type
                """,
                params,
            ).fetchall()

            revenue = Decimal("0.0")
            cogs = Decimal("0.0")
            operating_expenses = Decimal("0.0")

            for r in rows:
                code = r["account_code"]
                acc_type = r["account_type"]
                debit_val = Decimal(str(r["debit_sum"]))
                credit_val = Decimal(str(r["credit_sum"]))

                if acc_type == "REVENUE":
                    # Revenue normal credit: Credit - Debit
                    revenue += credit_val - debit_val
                elif acc_type == "EXPENSE":
                    # Expense normal debit: Debit - Credit
                    expense_val = debit_val - credit_val
                    if code.startswith("5"):
                        cogs += expense_val
                    else:
                        operating_expenses += expense_val

        gross_profit = revenue - cogs
        net_profit = gross_profit - operating_expenses

        return IncomeStatement(
            start_date=start_date,
            end_date=target_end_date,
            revenue=revenue,
            cogs=cogs,
            gross_profit=gross_profit,
            operating_expenses=operating_expenses,
            net_profit=net_profit,
        )

    def create_accounts_payable(
        self,
        po_id: str,
        supplier_name: str,
        amount: Decimal,
        grn_id: Optional[str] = None,
        due_days: int = 30,
    ) -> AccountsPayable:
        """Create a new AP record for procurement."""
        ap_id = f"AP-{uuid.uuid4().hex[:10].upper()}"
        due_date = datetime.date.today() + datetime.timedelta(days=due_days)

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO accounts_payable (ap_id, po_id, grn_id, supplier_name, due_date, amount, paid_amount, status)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (ap_id, po_id, grn_id, supplier_name, due_date.isoformat(), float(amount), APStatus.UNPAID.value),
            )

        return AccountsPayable(
            ap_id=ap_id,
            po_id=po_id,
            grn_id=grn_id,
            supplier_name=supplier_name,
            due_date=due_date,
            amount=amount,
            paid_amount=Decimal("0.0"),
            status=APStatus.UNPAID,
        )

    def get_ar_aging(self, as_of_date: Optional[date] = None) -> AgingReport:
        """Compute Accounts Receivable aging report grouped by buckets."""
        target_date = as_of_date or datetime.date.today()

        with self.db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT ar.ar_id, ar.order_id, ar.customer_id, ar.due_date, ar.amount, ar.paid_amount, ar.status
                FROM accounts_receivable ar
                WHERE ar.paid_amount < ar.amount AND ar.status != 'PAID'
                ORDER BY ar.due_date ASC
                """
            ).fetchall()

            items: List[AgingItem] = []
            total_outstanding = Decimal("0.0")
            current_amt = Decimal("0.0")
            days_1_30_amt = Decimal("0.0")
            days_31_60_amt = Decimal("0.0")
            days_60_plus_amt = Decimal("0.0")

            for r in rows:
                amount = Decimal(str(r["amount"]))
                paid = Decimal(str(r["paid_amount"]))
                outstanding = amount - paid
                total_outstanding += outstanding

                due_d = (
                    datetime.date.fromisoformat(r["due_date"])
                    if isinstance(r["due_date"], str)
                    else r["due_date"]
                )
                days_overdue = (target_date - due_d).days

                if days_overdue <= 0:
                    bucket = AgingBucket.CURRENT
                    current_amt += outstanding
                elif 1 <= days_overdue <= 30:
                    bucket = AgingBucket.DAYS_1_30
                    days_1_30_amt += outstanding
                elif 31 <= days_overdue <= 60:
                    bucket = AgingBucket.DAYS_31_60
                    days_31_60_amt += outstanding
                else:
                    bucket = AgingBucket.DAYS_60_PLUS
                    days_60_plus_amt += outstanding

                items.append(
                    AgingItem(
                        item_id=r["ar_id"],
                        reference_id=r["order_id"],
                        partner_name=r["customer_id"],
                        amount=amount,
                        paid_amount=paid,
                        outstanding_amount=outstanding,
                        due_date=due_d,
                        days_overdue=max(0, days_overdue),
                        bucket=bucket,
                        status=r["status"],
                    )
                )

        return AgingReport(
            report_type="RECEIVABLE",
            as_of_date=target_date,
            total_outstanding=total_outstanding,
            current_amount=current_amt,
            days_1_30_amount=days_1_30_amt,
            days_31_60_amount=days_31_60_amt,
            days_60_plus_amount=days_60_plus_amt,
            items=items,
        )

    def get_ap_aging(self, as_of_date: Optional[date] = None) -> AgingReport:
        """Compute Accounts Payable aging report grouped by buckets."""
        target_date = as_of_date or datetime.date.today()

        with self.db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT ap.ap_id, ap.po_id, ap.supplier_name, ap.due_date, ap.amount, ap.paid_amount, ap.status
                FROM accounts_payable ap
                WHERE ap.paid_amount < ap.amount AND ap.status != 'PAID'
                ORDER BY ap.due_date ASC
                """
            ).fetchall()

            items: List[AgingItem] = []
            total_outstanding = Decimal("0.0")
            current_amt = Decimal("0.0")
            days_1_30_amt = Decimal("0.0")
            days_31_60_amt = Decimal("0.0")
            days_60_plus_amt = Decimal("0.0")

            for r in rows:
                amount = Decimal(str(r["amount"]))
                paid = Decimal(str(r["paid_amount"]))
                outstanding = amount - paid
                total_outstanding += outstanding

                due_d = (
                    datetime.date.fromisoformat(r["due_date"])
                    if isinstance(r["due_date"], str)
                    else r["due_date"]
                )
                days_overdue = (target_date - due_d).days

                if days_overdue <= 0:
                    bucket = AgingBucket.CURRENT
                    current_amt += outstanding
                elif 1 <= days_overdue <= 30:
                    bucket = AgingBucket.DAYS_1_30
                    days_1_30_amt += outstanding
                elif 31 <= days_overdue <= 60:
                    bucket = AgingBucket.DAYS_31_60
                    days_31_60_amt += outstanding
                else:
                    bucket = AgingBucket.DAYS_60_PLUS
                    days_60_plus_amt += outstanding

                items.append(
                    AgingItem(
                        item_id=r["ap_id"],
                        reference_id=r["po_id"],
                        partner_name=r["supplier_name"],
                        amount=amount,
                        paid_amount=paid,
                        outstanding_amount=outstanding,
                        due_date=due_d,
                        days_overdue=max(0, days_overdue),
                        bucket=bucket,
                        status=r["status"],
                    )
                )

        return AgingReport(
            report_type="PAYABLE",
            as_of_date=target_date,
            total_outstanding=total_outstanding,
            current_amount=current_amt,
            days_1_30_amount=days_1_30_amt,
            days_31_60_amount=days_31_60_amt,
            days_60_plus_amount=days_60_plus_amt,
            items=items,
        )

    def settle_receivable(
        self,
        ar_id: str,
        amount: Optional[Decimal] = None,
        payment_account: str = "1101",
    ) -> JournalEntry:
        """Settle an accounts receivable receipt, update AR status, and record journal entry."""
        with self.db.transaction() as conn:
            ar_row = conn.execute(
                "SELECT ar_id, order_id, customer_id, amount, paid_amount FROM accounts_receivable WHERE ar_id = ?",
                (ar_id,),
            ).fetchone()
            if not ar_row:
                raise ValueError(f"查無應收帳款單號: {ar_id}")

            total_amount = Decimal(str(ar_row["amount"]))
            current_paid = Decimal(str(ar_row["paid_amount"]))
            remaining = total_amount - current_paid

            settle_amount = Decimal(str(amount)) if amount is not None else remaining
            if settle_amount <= Decimal("0.0"):
                raise ValueError(f"沖銷金額必須大於 0: {settle_amount}")
            if settle_amount > remaining:
                raise ValueError(f"沖銷金額 ({settle_amount}) 超過未收餘額 ({remaining})")

            new_paid = current_paid + settle_amount
            new_status = "PAID" if new_paid >= total_amount else "PARTIAL"

            conn.execute(
                "UPDATE accounts_receivable SET paid_amount = ?, status = ? WHERE ar_id = ?",
                (float(new_paid), new_status, ar_id),
            )

        # Record balanced journal entry: Dr Cash/Bank, Cr Accounts Receivable
        return self.create_journal_entry(
            entry_date=datetime.date.today(),
            source_event="AR_RECEIPT",
            reference_id=ar_id,
            description=f"收取客戶 {ar_row['customer_id']} 款項 (訂單 {ar_row['order_id']})",
            lines=[
                (payment_account, settle_amount, Decimal("0.0")),
                ("1144", Decimal("0.0"), settle_amount),
            ],
        )

    def settle_payable(
        self,
        ap_id: str,
        amount: Optional[Decimal] = None,
        payment_account: str = "1101",
    ) -> JournalEntry:
        """Settle an accounts payable payment, update AP status, and record journal entry."""
        with self.db.transaction() as conn:
            ap_row = conn.execute(
                "SELECT ap_id, po_id, supplier_name, amount, paid_amount FROM accounts_payable WHERE ap_id = ?",
                (ap_id,),
            ).fetchone()
            if not ap_row:
                raise ValueError(f"查無應付帳款單號: {ap_id}")

            total_amount = Decimal(str(ap_row["amount"]))
            current_paid = Decimal(str(ap_row["paid_amount"]))
            remaining = total_amount - current_paid

            settle_amount = Decimal(str(amount)) if amount is not None else remaining
            if settle_amount <= Decimal("0.0"):
                raise ValueError(f"沖銷金額必須大於 0: {settle_amount}")
            if settle_amount > remaining:
                raise ValueError(f"沖銷金額 ({settle_amount}) 超過未付餘額 ({remaining})")

            new_paid = current_paid + settle_amount
            new_status = "PAID" if new_paid >= total_amount else "PARTIAL"

            conn.execute(
                "UPDATE accounts_payable SET paid_amount = ?, status = ? WHERE ap_id = ?",
                (float(new_paid), new_status, ap_id),
            )

        # Record balanced journal entry: Dr Accounts Payable, Cr Cash/Bank
        return self.create_journal_entry(
            entry_date=datetime.date.today(),
            source_event="AP_PAYMENT",
            reference_id=ap_id,
            description=f"支付供應商 {ap_row['supplier_name']} 款項 (採購單 {ap_row['po_id']})",
            lines=[
                ("2144", settle_amount, Decimal("0.0")),
                (payment_account, Decimal("0.0"), settle_amount),
            ],
        )
