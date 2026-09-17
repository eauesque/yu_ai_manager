"""GitHub account management — re-export shim for backward compatibility.

Split into:
  - account_store_crud.py   (CRUD operations, token management)
  - account_store_triage.py (triage prompts, queue configuration)
"""

# CRUD: account and token management
from .account_store_crud import (  # noqa: F401
    add_account,
    get_account,
    list_accounts,
    remove_account,
    sync_token_settings,
    update_account,
)

# Triage: prompts, defaults, queue config
from .account_store_triage import (  # noqa: F401
    DEFAULT_TRIAGE_PROMPT_DISCUSSION,
    DEFAULT_TRIAGE_PROMPT_ISSUE,
    DEFAULT_TRIAGE_PROMPT_PR,
    TRIAGE_PROMPT_DEFAULTS,
    get_queue_config,
    get_triage_config,
    get_triage_prompts,
    get_triage_prompts_per_repo,
    save_queue_config,
    save_triage_prompts,
)
