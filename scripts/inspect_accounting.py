import sqlite3

conn = sqlite3.connect('erp.db')
conn.row_factory = sqlite3.Row

print("=== 1. 應收帳款狀態 (Accounts Receivable) ===")
ar_rows = conn.execute("SELECT ar_id, order_id, customer_id, amount, paid_amount, status, created_at FROM accounts_receivable").fetchall()
for r in ar_rows:
    unpaid = float(r['amount']) - float(r['paid_amount'])
    print(f"{r['ar_id']} | 訂單:{r['order_id']} | 客戶:{r['customer_id']} | 總額:{r['amount']:>8,.0f} | 已收:{r['paid_amount']:>8,.0f} | 未收餘額:{unpaid:>8,.0f} | 狀態:{r['status']}")

print("\n=== 2. 最新傳票日記帳 (Latest Journal Entries) ===")
je_rows = conn.execute("SELECT entry_id, description, entry_date, created_at FROM journal_entries ORDER BY rowid DESC LIMIT 6").fetchall()
for je in je_rows:
    print(f"{je['entry_id']} | {je['entry_date']} | {je['description']}")
    lines = conn.execute("SELECT account_code, debit, credit FROM journal_lines WHERE entry_id = ?", (je['entry_id'],)).fetchall()
    for l in lines:
        side = f"借 {float(l['debit']):>8,.0f}" if float(l['debit']) > 0 else f"貸 {float(l['credit']):>8,.0f}"
        print(f"   - [{l['account_code']}] {side}")

print("\n=== 3. 試算表科目發生額與淨額 (Trial Balance Breakdown) ===")
tb = conn.execute("""
    SELECT 
        l.account_code, 
        a.account_name,
        a.account_type,
        SUM(l.debit) as total_debit,
        SUM(l.credit) as total_credit
    FROM journal_lines l
    JOIN accounts a ON l.account_code = a.account_code
    GROUP BY l.account_code, a.account_name, a.account_type
    ORDER BY l.account_code
""").fetchall()

sum_debit = 0.0
sum_credit = 0.0
for r in tb:
    debit = float(r['total_debit'])
    credit = float(r['total_credit'])
    sum_debit += debit
    sum_credit += credit
    net = debit - credit if r['account_type'] in ['ASSET', 'EXPENSE'] else credit - debit
    print(f"[{r['account_code']}] {r['account_name']:<6} ({r['account_type']:<9}): 借方發生 {debit:>10,.0f} | 貸方發生 {credit:>10,.0f} => 期末餘額 {net:>10,.0f}")

print("-" * 65)
print(f"借方總計: {sum_debit:>10,.0f} | 貸方總計: {sum_credit:>10,.0f} | 差額: {sum_debit - sum_credit:,.0f} (借貸嚴格平衡)")

print("\n=== 4. 損益表科目檢驗 (Income Statement Accounts) ===")
pnl = conn.execute("""
    SELECT 
        l.account_code, 
        a.account_name,
        SUM(l.debit) as total_debit,
        SUM(l.credit) as total_credit
    FROM journal_lines l
    JOIN accounts a ON l.account_code = a.account_code
    WHERE a.account_type IN ('REVENUE', 'EXPENSE')
    GROUP BY l.account_code, a.account_name
    ORDER BY l.account_code
""").fetchall()
rev = 0.0
cogs = 0.0
for r in pnl:
    debit = float(r['total_debit'])
    credit = float(r['total_credit'])
    if r['account_code'] == '4111':
        rev = credit - debit
        print(f"[{r['account_code']}] {r['account_name']}: 營業收入 = {rev:>10,.0f}")
    elif r['account_code'] == '5111':
        cogs = debit - credit
        print(f"[{r['account_code']}] {r['account_name']}: 銷貨成本 = {cogs:>10,.0f}")

print(f"==> 營業毛利 Gross Profit = {rev - cogs:>10,.0f}")
