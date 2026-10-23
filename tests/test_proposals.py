from pathlib import Path
import json

import pytest

from context_hub.orchestration.models import ContextEvidence, ContextStatistics
from context_hub.proposals import ChangeProposal, ProposedFileDiff, ProposalGenerator, ProposalLimits
from context_hub.providers.config import ProviderSettings
from context_hub.providers.models import GenerationResponse


class Provider:
    def __init__(self, text): self.text = text
    def generate(self, request): return GenerationResponse(text=self.text, model="test", provider="test")


class Orchestrator:
    def __init__(self, *args, **kwargs): pass
    def build(self, task):
        class Packet:
            files = [ContextEvidence(id="1", path="app.py", source="retrieval", score=1, reason="match", content="old\n")]
        return Packet()


def payload(patch):
    return json.dumps({"summary":"Update app","rationale":"Improve behavior","files":[{"path":"app.py","patch":patch}],"assumptions":[],"risks":[],"validation_recommendations":["pytest"]})


def test_valid_diff_and_safe_save(tmp_path: Path):
    patch = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n"
    generator = ProposalGenerator(tmp_path, Provider(payload(patch)), settings=ProviderSettings(), limits=ProposalLimits())
    proposal = generator.generate("update app", packet=Orchestrator().build("x"))
    assert proposal.files[0].path == "app.py"
    saved = generator.save(proposal, Path(".context-hub/proposals"))
    assert saved.is_file() and "new" in saved.read_text()


@pytest.mark.parametrize("bad", [
    '{"summary":"x","rationale":"x","files":[{"path":"app.py","patch":"not a diff"}]}',
    '{"summary":"x","rationale":"x","files":[{"path":"../app.py","patch":"x"}]}',
    '{"summary":"x","rationale":"x","files":[{"path":"missing.py","patch":"--- a/missing.py\\n+++ b/missing.py\\n@@ -1 +1 @@\\n-a\\n+b"}]}',
])
def test_invalid_proposals_are_rejected(tmp_path, bad):
    generator = ProposalGenerator(tmp_path, Provider(bad), settings=ProviderSettings())
    with pytest.raises(ValueError): generator.generate("task", packet=Orchestrator().build("x"))


def test_limits_and_unsafe_artifact_destination(tmp_path):
    patch = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n"
    proposal = ChangeProposal(summary="x", rationale="x", files=[ProposedFileDiff(path="app.py", patch=patch)])
    generator = ProposalGenerator(tmp_path, Provider("{}"), limits=ProposalLimits(max_patch_chars=1000))
    with pytest.raises(ValueError): generator.save(proposal, Path(".."))
