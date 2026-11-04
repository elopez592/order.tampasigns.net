# Automatic email inquiries

Open `/staff#email-inquiries` (also available from CRM → Email inquiries).

An owner connects the AI reviewer with an OpenAI API key, then connects each Gmail / Google Workspace mailbox with its own Google app password. Keys/passwords are verified before saving, retained in a mode-0600 server-side file on the persistent data volume, and never returned by the API. These connections are separate from Gmail access inside ChatGPT. Google app passwords require 2-Step Verification and account policy permitting them.

The application checks enabled mailboxes every minute, while the website runs. No browser tab, ChatGPT automation, Gmail labels, or external cron service is required. The interval starts after the previous batch finishes. Each mailbox processes up to ten messages per batch. New connections begin at the current Gmail UID; historical mail is not imported automatically. Pausing retains the cursor so mail arriving during a pause is processed on resume.

Gmail All Mail must be exposed to IMAP. It is opened read-only and messages use BODY.PEEK, preserving read/unread state and labels. Spam and Trash are outside All Mail. Gmail thread history includes earlier incoming and outgoing messages for context; outgoing mail from connected addresses is skipped as an intake candidate. The AI sees email text, bounded conversation history, existing sender-owned inquiry/job context, and attachment filenames. It does not inspect attachment contents or follow external download links.

The AI classifies each candidate as a new inquiry, a project update, unrelated mail, or uncertain. Low-confidence skips become inquiries needing clarification. New inquiries create/link CRM contacts without changing existing contact status, pricing, proof decisions, customer terms, or payment records. Automatically created contacts have outbound reminders off. Reply matching uses Gmail thread IDs, email reference headers, and AI-selected sender-owned records. A new project within an existing thread can become a separate inquiry.

The private dashboard shows summaries, extracted specifications, requested deadlines, missing details, original incoming messages, attachments, and recent classification reasons. Raw HTML is not rendered. Attachments require owner access and are served as forced downloads. Original attachments remain available even when their file type is not supported by the artwork upload pipeline.

An owner may link an inquiry to an existing job for that sender or create a draft quote/job. The draft has no invented dimensions or prices, starts unpublished with the normal workflow gates, and opens in the existing quote editor. Add and review the quote lines before publishing. Supported PNG/JPEG/PDF artwork is copied into the job; other originals stay with the inquiry. Conversion is idempotent. Linked inquiries appear under the job's Activity tab.

A database lease prevents overlapping checks. Each processed message is recorded transactionally before advancing its durable UID cursor; failed AI calls or parsing/import failures leave the cursor unchanged and retry. Message IDs prevent duplicate imports. A Gmail UIDVALIDITY change stops that mailbox and asks the owner to reconnect rather than guessing which messages to skip. Connection errors are shown per mailbox without logging credentials. Settings and data are isolated by company workspace. The root process also checks configured, accessible tenant workspaces.

## Verification

Run `python -m pytest -q tests/test_email_intake.py tests/test_crm.py tests/test_crm_client_accounts.py tests/test_editable_quote_lines.py tests/test_company_platform.py` and JavaScript syntax checks. Tests use simulated Gmail and AI responses, verifying real database writes, permissions, retries, deduplication, thread handling, record ownership, attachment protection, and draft quote editing. Live Gmail and AI verification requires the owner's credentials and a real inbound test message.
