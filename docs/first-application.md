# Prepare your first application

After onboarding is ready, tell your agent:

> Help me prepare an application for this job. Use my confirmed experience, show me gaps, and do not submit anything.

Provide a job URL or the full posting text. If browsing is unavailable, paste or save the posting yourself. The agent should:

1. Preserve the posting and capture an opportunity, without immediately creating an application.
2. Evaluate it against your confirmed facts and preferences. Missing evidence is a question, not permission to invent experience.
3. Ask whether you want to pursue it. The engine creates the application through `opportunity pursue`, not an `application create` command.
4. Draft job-specific documents in the application's drafts folder.
5. Validate and create immutable document releases when rendering/inspection tools are available, then create portal-safe upload copies.
6. Show you the actual files and any remaining gaps.

Without rendering tools, the agent may hand over text drafts but must not call them validated PDFs. Without a browser, it can still prepare documents and explain how you can use them yourself. Do not invent form fields or mark a manually submitted application as confirmed without attributable evidence.

## Optional experimental portal work

Browser-assisted submission is not part of ordinary setup or preparation. It needs an explicit request, real observed form fields, separately governed sensitive answers, an exact payload, trusted final approval, immediate revalidation, and observed employer confirmation.

An uncertain result stays uncertain. A click is not proof of submission, and the agent must not retry a potentially successful submission.

[Agent command examples and request schemas](agent-workflows.md) cover the underlying contracts.
