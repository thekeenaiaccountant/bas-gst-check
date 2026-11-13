# Xero access

This checker does not log into Xero. It does not send your file anywhere, and it does not change Xero. The normal way to use it is an export.

Practise on **Xero's Demo Company** before you point it at a live file. The Demo Company is the sample organisation already in a Xero login. It is not your client's books.

## Default: no connection

Export these three things for the same dates as the BAS, and the same cash or accrual basis you lodge on.

1. **Account Transactions.** This is the file the checker reads.
   Reporting, All reports, search for Account Transactions. Set the dates. Under More, choose Cash or Accrual to match the BAS. Update, then export to Excel.
   [Xero: report settings, including export](https://central.xero.com/s/article/Select-contents-and-display-order-in-a-new-report).
2. **Bills.** Business menu, Purchases, Bills. Use the menu beside New bill and choose Export if you want the list (CSV, and Xero caps one export at about 500 bills). Also save the bill PDFs or photos into one folder. The checker matches those files to the export. It does not open Xero to fetch them.
3. **GST transactions, as a cross-check.** Inside the GST return, Xero can list the transactions that make up the return. Xero says that list is part of the return and is not a separate report you generate on its own.
   [Xero: view transactions on your GST return](https://central.xero.com/0/article/The-GST-Audit-Report).
   The GST Reconciliation report, under Reporting, All reports, is a useful total to sit beside the draft 1A and 1B. The line-by-line check still uses Account Transactions.

Excel (`.xlsx`) and CSV both open. There is no extra fee from this tool for an export. Exporting is part of the Xero organisation you already use.

A previous quarter, if you have one, can be a second Account Transactions export. Pass it when you run the check, or leave it for the next run to remember on this computer. It is how new suppliers and a jump in spend are spotted.

## Optional: a read-only connection

You do not need this. Use it only if Claude or Codex already has a Xero connector, a Xero plugin, or an MCP server, and you would rather it read the same things instead of you exporting them.

Ask for **read** scopes only. The names below were checked against Xero's scope list and the March 2026 change that split the broad scopes into smaller ones.

- Scope list: [Xero OAuth 2.0 scopes](https://developer.xero.com/documentation/guides/oauth2/scopes/)
- What changed: [Xero changelog, broad scopes](https://developer.xero.com/changelog) and [granular scopes FAQ](https://developer.xero.com/faq/granular-scopes)
- The write-up of the split: [Upcoming changes to Xero Accounting API scopes](https://devblog.xero.com/upcoming-changes-to-xero-accounting-api-scopes-705c5a9621a0)

Apps created on or after 2 March 2026 use the smaller names. Apps created before that can still use the older broad names until 13 September 2027. Settings, contacts and attachments kept the same names.

| Scope | Why it is needed | Which check uses it |
| --- | --- | --- |
| `accounting.invoices.read` | Read bills and sales invoices, including the GST on each line. This is the bills part of the older `accounting.transactions.read`. | Bill-to-ledger match. GST on the bill versus GST in the file. |
| `accounting.banktransactions.read` | Read spend and receive money that never became a bill. This is the bank part of the older `accounting.transactions.read`. | Bill-to-ledger match. New or jumped suppliers. |
| `accounting.payments.read` | Read which bills were paid, so a cash-basis quarter uses the payments in the period. Part of the older `accounting.transactions.read`. | Bill-to-ledger match when the file is cash basis. |
| `accounting.contacts.read` | Read supplier names. This name did not change. | Bill-to-ledger match. New or jumped suppliers. |
| `accounting.settings.read` | Read the tax rates, such as GST on Expenses, GST Free and BAS Excluded. This name did not change. | Suggested GST code. |
| `accounting.attachments.read` | Read a PDF or photo attached to a bill. This name did not change. | Bill-to-ledger match. GST on the bill versus the file. |

`accounting.transactions.read` is the old broad name. If a connector still shows only that, it covers invoices, bank transactions and payments until 13 September 2027, for an app created before 2 March 2026. Prefer the three `.read` names in the table when the connector lets you tick them separately.

`accounting.reports.read` is also an old name. Xero replaced it with separate report scopes such as `accounting.reports.profitandloss.read`, `accounting.reports.balancesheet.read`, `accounting.reports.trialbalance.read` and `accounting.reports.aged.read`. This checker does not need those. The line check uses the transactions, not the profit and loss.

`offline_access` only lets a connector refresh the login later without asking again. This checker does not store a token. Ask for `offline_access` only if the connector says it cannot stay signed in without it.

### What it does not need

- No write scopes. Do not tick `accounting.invoices`, `accounting.payments`, `accounting.banktransactions`, `accounting.manualjournals`, `accounting.contacts` or `accounting.attachments` without `.read`. Those can change Xero.
- No payroll scopes.
- No bank-feed write, and no permission to create spend money.
- No permission to upload or delete files.
- No `accounting.journals.read`. That journals endpoint is not granted by default. Xero says it needs the Advanced tier and certification. The Account Transactions export already includes journal lines, so the export path does not need it.
- No permission to publish or lodge a BAS.

The official Xero MCP server documents the same old and new names and links to the scopes page above. A connector that asks for payroll, or for any scope without `.read`, is asking for more than this check uses. Say no.

There is no extra charge from this tool. Reading through a connector uses whatever access that app already has. Do not buy a Xero API tier for this check. The export path is enough.
