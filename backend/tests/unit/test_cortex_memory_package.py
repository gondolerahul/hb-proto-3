"""cortex_memory package — boundary + provider contract (Phase 12 `04` Stage B).

Verifies the extraction's core invariant (the package imports with **no host
dependency**), that the provider Protocols are satisfied by the reference
implementations, and that the host's ``scope_policy`` re-export shim still works.
"""
from __future__ import annotations

import pytest

import cortex_memory
from cortex_memory.providers import (
    EmbeddingProvider,
    LLMProvider,
    RunRegistry,
    UsageReporter,
)
from cortex_memory.providers_reference import (
    EchoLLMProvider,
    HashEmbeddingProvider,
    InMemoryRunRegistry,
    NullUsageReporter,
)


def test_package_has_no_host_imports() -> None:
    """The extraction's core invariant: no ``cortex_memory`` source file may
    import the host (``src.ai.*`` / ``src.*``)."""
    import pathlib

    pkg_dir = pathlib.Path(cortex_memory.__file__).parent
    offenders = []
    for py in pkg_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("from src.", "import src.", "from src ", "import src")):
                offenders.append(f"{py.name}: {stripped}")
    assert not offenders, "cortex_memory must not import the host:\n" + "\n".join(offenders)


def test_reference_providers_satisfy_protocols() -> None:
    assert isinstance(EchoLLMProvider(), LLMProvider)
    assert isinstance(HashEmbeddingProvider(), EmbeddingProvider)
    assert isinstance(NullUsageReporter(), UsageReporter)
    assert isinstance(InMemoryRunRegistry(), RunRegistry)


@pytest.mark.asyncio
async def test_echo_llm_provider() -> None:
    res = await EchoLLMProvider().complete(system="sys", user="hello world")
    assert "hello world" in res.text
    assert res.model == "echo-llm"
    assert res.output_tokens > 0


@pytest.mark.asyncio
async def test_hash_embedding_provider_deterministic() -> None:
    p = HashEmbeddingProvider(dim=8)
    a = await p.embed(["alpha", "beta"])
    b = await p.embed(["alpha", "beta"])
    assert a.dimension == 8
    assert a.vectors == b.vectors  # deterministic
    assert a.char_count == len("alpha") + len("beta")


@pytest.mark.asyncio
async def test_in_memory_run_registry() -> None:
    reg = InMemoryRunRegistry()
    reg.add(cortex_memory.RunRef(run_id="r1", company_id="c1"))
    got = await reg.get_run("r1")
    assert got is not None and got.company_id == "c1"
    assert await reg.get_run("missing") is None


def test_scope_policy_exported_from_package_root() -> None:
    sp = cortex_memory.ScopePolicy.child_recursion_default()
    assert sp.can_read_outside is True and sp.can_write_outside is False
    assert issubclass(cortex_memory.ScopeViolation, RuntimeError)


def test_host_scope_policy_reexport_is_same_object() -> None:
    """The host shim re-exports the package's classes (identity, not a copy)."""
    from src.ai.memory.scope_policy import ScopePolicy, ScopeViolation

    assert ScopePolicy is cortex_memory.ScopePolicy
    assert ScopeViolation is cortex_memory.ScopeViolation
