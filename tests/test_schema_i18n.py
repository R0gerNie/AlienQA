"""Unreadable saved results report validation failures in the active language."""
import pytest

from alienqa.evidence import Evidence
from alienqa.i18n import language_context
from alienqa.review import ReviewState


@pytest.mark.parametrize('document, message', [
    ({'schema_version': 999}, 'Unsupported Evidence schema_version'),
    ({'finding_kind': 'unknown'}, 'Invalid finding_kind'),
    ({'finding_kind': 'cognitive_mismatch'}, 'Cognitive evidence has no valid prior expectation basis'),
    ({'finding_kind': 'technical_anomaly', 'expectation_basis': {}}, 'Technical evidence cannot invent a cognitive basis'),
])
def test_evidence_validation_errors_are_english(document, message):
    with language_context('en'), pytest.raises(ValueError, match=message):
        Evidence.from_dict(document)


@pytest.mark.parametrize('document, message', [
    ([], 'Review state must be a JSON object'),
    ({'EV': []}, 'Invalid review record'),
    ({'EV': {'decision': 'rejected', 'note': []}}, 'Note must be a string'),
    ({'EV': {'decision': 'unknown'}}, 'Invalid review decision'),
])
def test_review_validation_errors_are_english(document, message):
    with language_context('en'), pytest.raises(ValueError, match=message):
        ReviewState.from_dict(document)
