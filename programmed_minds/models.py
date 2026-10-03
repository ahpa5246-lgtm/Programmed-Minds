"""Strict handoff contracts. Prompts cannot extend these contracts."""
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, field_validator

TOOLS = ('superpowers','qodo','asvs','semgrep','gitleaks','osv','trivy','zap','pgtap','playwright','lighthouse','size-limit','k6')

class Contract(BaseModel):
    model_config=ConfigDict(extra='forbid', strict=True)

class Source(Contract):
    id:str=Field(min_length=1)
    title:str=Field(min_length=1)
    url:str
    supports:str=Field(min_length=1)
    accessed_at:str=Field(min_length=1)
    @field_validator('url')
    @classmethod
    def safe_url(cls,value):
        url=urlsplit(value)
        if url.scheme not in ('https','http') or not url.hostname or url.username or url.password or any(ord(c)<33 for c in value):
            raise ValueError('Source must be an HTTP(S) URL without credentials or whitespace')
        return value

class Idea(Contract):
    id:str
    title:str
    problem:str
    audience:str
    differentiation:str
    evidence_ids:list[str]=Field(min_length=1)
    novelty:Literal['supported','hypothesis','unknown']
    winning_evidence:str # empty unless award is documented

class Research(Contract):
    summary:str
    ideas:list[Idea]=Field(min_length=1)
    sources:list[Source]=Field(min_length=1)
    unknowns:list[str]

class Requirement(Contract):
    id:str
    description:str
    acceptance:str
    origin:str
    evidence_tool:Literal['playwright','python-tests','pgtap','manual']
    test_id:str=Field(min_length=1)

class StrategyAssessment(Contract):
    decision:Literal['go','clarify','stop']
    judging_basis:str=Field(min_length=1)
    differentiation:str=Field(min_length=1)
    strongest_rival:str=Field(min_length=1)
    failure_scenario:str=Field(min_length=1)
    disconfirming_test:str=Field(min_length=1)
    evidence_ids:list[str]=Field(min_length=1)
    unknowns:list[str]

class Improvement(Contract):
    selected_idea_id:str
    concept:str
    changes:list[str]=Field(min_length=1)
    requirements:list[Requirement]=Field(min_length=1)
    competition_fit:list[str]
    feasibility:str
    risks:list[str]
    excluded_scope:list[str]
    strategy_assessment:StrategyAssessment|None

class Task(Contract):
    id:str
    title:str
    files:list[str]=Field(min_length=1)
    depends_on:list[str]
    requirement_ids:list[str]=Field(min_length=1)
    acceptance:list[str]=Field(min_length=1)
    tools:list[str]

class Gate(Contract):
    tool:str
    applicable:bool
    required:bool
    reason:str=Field(min_length=1)
    evidence:str=Field(min_length=1)

class Plan(Contract):
    architecture:str
    stack:list[str]=Field(min_length=1)
    tasks:list[Task]=Field(min_length=1)
    gates:list[Gate]
    asvs_mapping:list[str]
    delivery_steps:list[str]=Field(min_length=1)

class Design(Contract):
    direction:str
    palette:list[str]=Field(min_length=4,max_length=6)
    typography:str
    user_flows:list[str]=Field(min_length=1)
    components:list[str]=Field(min_length=1)
    accessibility:list[str]=Field(min_length=1)
    responsive_rules:list[str]=Field(min_length=1)
    sources:list[Source]=Field(min_length=1)
    license_notes:list[str]=Field(min_length=1)

class Issue(Contract):
    severity:Literal['critical','high','medium','low']
    claim:str=Field(min_length=1)
    evidence:str=Field(min_length=1)
    fix:str=Field(min_length=1)

class Review(Contract):
    verdict:Literal['approve','revise','reject']
    summary:str
    issues:list[Issue]
    questions:list[str]

class TestCase(Contract):
    requirement_id:str
    scenario:str
    steps:list[str]=Field(min_length=1)
    expected:str
    evidence:str # actual report/log path; empty if unexecuted
    status:Literal['passed','failed','not_run']

class Audit(Contract):
    verdict:Literal['pass','block']
    summary:str
    cases:list[TestCase]=Field(min_length=1)
    gaps:list[str]
    issues:list[Issue]

SCHEMAS={'researcher':Research,'improver':Improvement,'planner':Plan,'designer':Design,'tester':Audit,
         'research_critic':Review,'improvement_critic':Review,'plan_critic':Review}
