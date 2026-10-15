import sqlite3

conn = sqlite3.connect('erp.db')
conn.row_factory = sqlite3.Row

print("=== 4111 銷貨收入明細 ===")
rev_lines = conn.execute("""
    SELECT je.entry_id, je.description, jl.credit, jl.debit 
    FROM journal_lines jl 
    JOIN journal_entries je ON jl.entry_id = je.entry_id 
    WHERE jl.account_code = '4111'
""").fetchall()
for r in rev_lines:
    print(f"{r['entry_id']} | 貸方收入: {r['credit']:>10,.2f} | 描述: {r['description']}")

print("\n=== 5111 銷貨成本明細 ===")
cogs_lines = conn.execute("""
    SELECT je.entry_id, je.description, jl.debit, jl.credit 
    FROM journal_lines jl 
    JOIN journal_entries je ON jl.entry_id = je.entry_id 
    WHERE jl.account_code = '5111'
""").fetchall()
for r in cogs_lines:
    print(f"{r['entry_id']} | 借方成本: {r['debit']:>10,.2f} | 描述: {r['description']}")

print("\n=== 6101 營業費用明細 ===")
exp_lines = conn.execute("""
    SELECT je.entry_id, je.description, jl.debit, jl.credit 
    FROM journal_lines jl 
    JOIN journal_entries je ON jl.entry_id = je.entry_id 
    WHERE jl.account_code = '6101'
""").fetchall()
for r in exp_lines:
    print(f"{r['entry_id']} | 借方費用: {r['debit']:>10,.2f} | 描述: {r['description']}")
