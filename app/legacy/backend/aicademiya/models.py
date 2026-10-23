"""Validated write payloads. Response projection lives in the service layer."""
from typing import Literal
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator


def validate_new_password(value):
    if not 8 <= len(value) <= 512 or not any(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ" for c in value) or not any(c in "0123456789" for c in value):
        raise ValueError("Use 8–512 characters including a letter and a digit")
    return value


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DemoLogin(Payload):
    role: Literal["teacher", "student", "admin"]
    student_index: Literal[1, 2] = 1


class Login(Payload):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=512)


class Register(Login):
    name: str = Field(min_length=1, max_length=100)
    join_code: str = Field(min_length=1, max_length=100)

    @field_validator("password")
    @classmethod
    def password_length(cls, value):
        return validate_new_password(value)


class ProvisionStudent(Payload):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    # Validation is deferred until account lookup: an existing Student can be
    # enrolled without a temporary password and must never have credentials reset.
    temporary_password: str | None = Field(default=None, max_length=512)

    @field_validator('temporary_password')
    @classmethod
    def optional_password(cls, value):
        return validate_new_password(value) if value else value


class GlobalAccountCreate(Payload):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    role: Literal['admin', 'teacher', 'student']
    temporary_password: str = Field(min_length=8, max_length=512)

    _validate_password = field_validator('temporary_password')(validate_new_password)


class GlobalRoleChange(Payload):
    role: Literal['admin', 'teacher', 'student']


class AccountStatus(Payload):
    active: StrictBool


class StaffAssignment(Payload):
    user_id: str = Field(min_length=1, max_length=200)


class ChangePassword(Payload):
    current_password: str = Field(max_length=512)
    new_password: str = Field(min_length=8, max_length=512)

    _validate_password = field_validator("new_password")(validate_new_password)


class JoinCourse(Payload):
    join_code: str = Field(min_length=1, max_length=100)


class CourseCreate(Payload):
    title: str = Field(min_length=1, max_length=300)
    code: str = Field(min_length=1, max_length=50)
    description: str = Field(default="", max_length=10000)


class CoursePatch(Payload):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    code: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=10000)

    @field_validator("title", "code", "description")
    @classmethod
    def valid_text(cls, value, info):
        if value is None or (info.field_name in ("title", "code") and not value.strip()):
            raise ValueError("Course fields must not be null; title and code must not be blank")
        return value


class TeachingProfile(Payload):
    schema_version: Literal[1] = 1
    background: str = Field(default="", max_length=8000)
    student_profile: str = Field(default="", max_length=8000)
    response_strategies: str = Field(default="", max_length=8000)
    tone: str = Field(default="Supportive, specific and respectful; avoid excessive praise.", max_length=1000)
    response_detail: Literal["concise", "balanced", "detailed"] = "balanced"
    phases: list[Literal["warmup", "worksheet", "quiz", "reading", "wrap_up"]] = Field(default_factory=lambda: ["warmup", "worksheet", "quiz", "wrap_up"])
    reading_focus: str = Field(default="", max_length=8000)
    reading_question_count: StrictInt = Field(default=3, ge=1, le=5)
    reference_delivery: Literal["on_request", "after_sufficient_answer"] = "after_sufficient_answer"
    idle_hint_seconds: StrictInt = 0
    presentation: Literal["full", "paced"] = "full"

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_schema(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("Teaching profile schema_version must be the integer 1")
        return value

    @model_validator(mode="after")
    def sequence(self):
        if len(self.phases) != len(set(self.phases)) or "worksheet" not in self.phases or not self.phases or self.phases[-1] != "wrap_up":
            raise ValueError("Use unique phases including worksheet and a final wrap_up")
        if "warmup" in self.phases and self.phases[0] != "warmup":
            raise ValueError("Warmup must be first")
        if "quiz" in self.phases and self.phases.index("quiz") < self.phases.index("worksheet"):
            raise ValueError("Quiz must follow worksheet")
        if "reading" in self.phases and self.phases.index("reading") < self.phases.index("worksheet"):
            raise ValueError("Reading discussion must follow worksheet")
        if self.idle_hint_seconds != 0 and not 10 <= self.idle_hint_seconds <= 300:
            raise ValueError("Idle hint seconds must be 0 or 10–300")
        return self


class SessionCreate(Payload):
    teaching_language: str = Field(default="en", min_length=1, max_length=100)
    teaching_profile: TeachingProfile | None = None
    title: str = Field(min_length=1, max_length=300)
    subtitle: str = Field(default="", max_length=1000)
    number: int = Field(default=1, ge=1)
    instructions: str = Field(default="", max_length=30000)
    learning_objectives: list[str] = Field(default_factory=list)


class Image(Payload):
    label: str = ""
    url: str = ""
    alt: str = ""
    asset_key: str | None = None


class Question(Payload):
    id: str = Field(min_length=1, max_length=200)
    group_id: str
    ordinal: int = Field(ge=1)
    type: Literal["open_response", "reading_response", "fill_in_blank", "single_choice", "image_matching"]
    prompt: str = Field(min_length=1, max_length=30000)
    options: list[str] = Field(default_factory=list)
    answer_slots: int = Field(default=1, ge=1)
    images: list[Image] = Field(default_factory=list)
    source_label: str = ""
    hint: str | None = None
    source_material_ids: list[str] = Field(default_factory=list, max_length=200)
    source_links: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("prompt")
    @classmethod
    def meaningful(cls, value):
        if not value.strip():
            raise ValueError("Question prompt must not be blank")
        return value


class Group(Payload):
    id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    kind: Literal["core", "reading"] = "core"
    description: str = Field(default="", max_length=10000)

    @field_validator("title")
    @classmethod
    def meaningful(cls, value):
        if not value.strip():
            raise ValueError("Group title must not be blank")
        return value


class SessionPatch(Payload):
    teaching_profile: TeachingProfile | None = None
    number: int | None = Field(default=None, ge=1, le=9999)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    subtitle: str | None = None
    instructions: str | None = Field(default=None, max_length=30000)
    learning_objectives: list[str] | None = None
    reference_policy: Literal["after_attempt", "after_feedback", "after_submit"] | None = None
    teaching_language: str | None = None
    status: Literal["draft", "published"] | None = None
    questions: list[Question] | None = None
    groups: list[Group] | None = None
    reference_answers: dict[str, str] | None = None
    active: bool | None = None
    starts_at: str | None = None
    ends_at: str | None = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def aware_time(cls, value):
        if value is not None:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.utcoffset() is None:
                    raise ValueError()
            except ValueError:
                raise ValueError("Use a timezone-aware ISO datetime") from None
        return value


class TeachingPreview(Payload):
    reference_policy: Literal["after_attempt", "after_feedback", "after_submit"] | None = None
    teaching_profile: TeachingProfile | None = None
    instructions: str | None = Field(default=None, max_length=30000)
    learning_objectives: list[str] | None = None
    teaching_language: str | None = Field(default=None, max_length=100)


class TutorStart(Payload):
    request_id: str | None = Field(default=None, min_length=1, max_length=200)
    preview_id: str | None = Field(default=None, min_length=1, max_length=200)


class TutorTurn(Payload):
    message: str = Field(min_length=1, max_length=30000)
    request_id: str = Field(min_length=1, max_length=200)
    preview_id: str | None = Field(default=None, min_length=1, max_length=200)
    web_search: bool = False
    action: Literal["message", "hint", "skip_quiz", "review_question"] = "message"
    question_id: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("message")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Message must not be blank")
        return value


class ReadingChoice(Payload):
    group_id: str = Field(min_length=1, max_length=200)


class PreviewReset(Payload):
    expected_revision: str = Field(min_length=1, max_length=200)


class SourceReviewInput(TeachingPreview):
    question_id: str | None = Field(default=None, min_length=1, max_length=200)
    phase: Literal["warmup", "worksheet", "quiz", "reading", "wrap_up", "complete"] = "worksheet"


class Answer(Payload):
    answer: str = Field(min_length=1, max_length=30000)

    @field_validator("answer")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Answer must not be blank")
        return value


class Chat(Payload):
    message: str = Field(min_length=1, max_length=30000)
    question_id: str | None = None
    intent: Literal["answer", "ask"]
    web_search: bool = False
    request_id: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("message")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Message must not be blank")
        return value


class Review(Payload):
    status: Literal["confirmed", "needs_revision"]
    note: str = Field(default="", max_length=10000)


class Settings(Payload):
    mode: Literal["demo", "openai"]
    base_url: str = Field(max_length=2000)
    model: str = Field(max_length=300)
    api_key: str | None = Field(default=None, max_length=10000)


class SearchSettings(Payload):
    enabled: bool | None = None
    api_key: str | None = Field(default=None, max_length=10000)
    clear_api_key: bool = False

    @model_validator(mode="after")
    def key_action(self):
        if self.clear_api_key and self.api_key and self.api_key.strip():
            raise ValueError("Choose either replacing or clearing the search API key")
        return self


class Empty(Payload):
    pass


class Profile(Payload):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Name must not be blank")
        return value.strip()


class StudentBatch(Payload):
    user_ids: list[str] = Field(min_length=1, max_length=1000)

    @field_validator("user_ids")
    @classmethod
    def unique_ids(cls, value):
        if len(value) != len(set(value)) or any(not x for x in value):
            raise ValueError("Supply unique nonempty user IDs")
        return value


class Publish(Payload):
    label: str | None = Field(default=None, max_length=300)


class LinkCreate(Payload):
    url: str = Field(min_length=1, max_length=2000)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    visibility: Literal["student", "teacher"] = "student"


class MaterialPatch(Payload):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    kind: Literal["reading", "worksheet", "answer_key", "slides", "reference"] | None = None
    visibility: Literal["student", "teacher"] | None = None
    url: str | None = Field(default=None, min_length=1, max_length=2000)


class MaterialAttach(Payload):
    material_id: str = Field(min_length=1, max_length=200)


class WorksheetCommit(Payload):
    groups: list[Group] = Field(max_length=200)
    questions: list[Question] = Field(max_length=1000)
    reference_answers: dict[str, str]
    mode: Literal["append", "replace"]
