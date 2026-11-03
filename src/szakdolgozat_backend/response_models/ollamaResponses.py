from pydantic import BaseModel, ConfigDict


class OllamaGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    response: str
    done: bool

    done_reason: str | None = None

    total_duration: int | None = None
    load_duration: int | None = None

    prompt_eval_count: int | None = None
    prompt_eval_duration: int | None = None

    eval_count: int | None = None
    eval_duration: int | None = None
