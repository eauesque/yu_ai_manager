LLM_TIMEOUTS: dict[str, float] = {
    "connect": 5.0,
    "first_byte": 60.0,
    "inter_token": 30.0,
    "total": 600.0,
}
IMAGE_TIMEOUTS: dict[str, float] = {
    "connect": 5.0,
    "first_progress": 60.0,
    "inter_progress": 120.0,
    "total": 1800.0,
}
