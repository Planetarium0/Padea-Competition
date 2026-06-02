# On direction

Do we need a system to automate the handling of edge cases?

- Possibly redirect WARNING or ERROR level logs to an LLM

Other thoughts:
1) Increase documentation, so that the AI knows specifically the general workflow and implementation of a script.
2) Increase logging, specifically, if an assumption is made about the integrity of the data, error handling for the case that the assumption does not hold must be handled. For example, if we assume site managers only have one phone number - and then we get something that can be passed to an AI to work on - for example, the script could error on something like a UnhandledEdgeCaseError.
3) Enforce testing before pushing to production.



