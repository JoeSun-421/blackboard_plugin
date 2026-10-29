"""Tests for the Interactive Technical Quiz Suite and Runner Engine."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quiz import QuizRunner, load_quiz_data


@pytest.fixture
def repo_root() -> Path:
    """Fixture providing the absolute path to the repository root."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def quiz_runner() -> QuizRunner:
    """Fixture providing an instantiated QuizRunner."""
    return QuizRunner()


def test_quiz_data_schema_and_completeness(quiz_runner: QuizRunner):
    """Verify that quiz_data.json satisfies all schema and completeness requirements."""
    is_valid, errors = quiz_runner.validate_data()
    assert is_valid, f"Quiz validation failed with errors: {errors}"
    assert len(errors) == 0

    data = quiz_runner.data
    assert data["total_points"] == 100
    assert data["passing_score"] == 70
    assert len(data["categories"]) >= 6

    questions = data["questions"]
    assert len(questions) >= 8

    mcqs = [q for q in questions if q.get("type") == "mcq"]
    analyses = [q for q in questions if q.get("type") == "analysis"]

    assert len(mcqs) == 6
    assert len(analyses) == 2

    for mcq in mcqs:
        assert mcq["points"] == 10
        assert set(mcq["options"].keys()) == {"A", "B", "C", "D"}
        assert mcq["answer"] in {"A", "B", "C", "D"}
        assert len(mcq["explanation"]) > 50
        assert "rubric" in mcq

    for analysis in analyses:
        assert analysis["points"] == 20
        assert len(analysis["answer"]) > 100
        criteria = analysis["rubric"]["criteria"]
        assert len(criteria) == 4
        assert sum(c["points"] for c in criteria) == 20


def test_quiz_data_topics_coverage(quiz_runner: QuizRunner):
    """Verify that all required MCQ and Analysis technical topics are covered."""
    questions = quiz_runner.questions
    all_text = " ".join([
        f"{q.get('question', '')} {q.get('explanation', '')} {q.get('category', '')} {q.get('answer', '')}"
        for q in questions
    ]).lower()

    # Required MCQ topics
    assert "sys.stdout = sys.stderr" in all_text or "sys.stdout" in all_text
    assert "2024-11-05" in all_text
    assert "9222" in all_text and "9229" in all_text and "9333" in all_text
    assert "msedge" in all_text and "chrome" in all_text and "chromium" in all_text
    assert "save_session" in all_text
    assert "to_dict" in all_text or "mask_secrets" in all_text
    assert "sts.cuhk.edu.hk" in all_text or "auth-saml" in all_text
    assert "action=logout" in all_text
    assert "re.sub" in all_text or "safe_filename" in all_text or "[\\\\/*?:\"<>|]" in all_text
    assert "57" in all_text or "offline" in all_text

    # Required Analysis topics
    assert "sso" in all_text or "adfs" in all_text
    assert "duo" in all_text
    assert "x-blackboard-sxs" in all_text
    assert "dual-engine" in all_text or "fallback" in all_text
    assert "beautifulsoup" in all_text or "bs4" in all_text


def test_quiz_data_code_citations_exist(quiz_runner: QuizRunner, repo_root: Path):
    """Verify that all code citations in quiz_data.json point to actual existing files."""
    for q in quiz_runner.questions:
        refs = q.get("code_references", [])
        assert len(refs) > 0, f"Question {q.get('id')} has no code references."
        for ref in refs:
            file_rel = ref.get("file")
            assert file_rel, f"Code reference in {q.get('id')} has no file path."
            cited_path = repo_root / file_rel
            assert cited_path.is_file(), f"Cited file does not exist: {cited_path}"


def test_quiz_data_loader(tmp_path: Path):
    """Test load_quiz_data helper function and error handling."""
    data = load_quiz_data()
    assert isinstance(data, dict)
    assert "questions" in data

    non_existent = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError):
        load_quiz_data(non_existent)


def test_quiz_runner_perfect_evaluation(quiz_runner: QuizRunner):
    """Verify scoring logic with 100% correct answers."""
    answers = {}
    for q in quiz_runner.questions:
        if q["type"] == "mcq":
            answers[q["id"]] = q["answer"]
        else:
            answers[q["id"]] = q["points"]

    result = quiz_runner.evaluate_answers(answers)
    assert result.total_points_earned == 100
    assert result.total_points_possible == 100
    assert result.percentage == 100.0
    assert result.passed is True

    result_dict = result.to_dict()
    assert result_dict["passed"] is True
    assert len(result_dict["question_results"]) == len(quiz_runner.questions)


def test_quiz_runner_incorrect_mcq_evaluation(quiz_runner: QuizRunner):
    """Verify point deductions and percentage calculation when MCQs are answered incorrectly."""
    answers = {}
    mcqs = [q for q in quiz_runner.questions if q["type"] == "mcq"]
    analyses = [q for q in quiz_runner.questions if q["type"] == "analysis"]

    # Answer all MCQs wrong
    for q in mcqs:
        correct = q["answer"]
        wrong = "A" if correct != "A" else "B"
        answers[q["id"]] = wrong

    # Answer all analysis full credit (40 pts)
    for q in analyses:
        answers[q["id"]] = q["points"]

    result = quiz_runner.evaluate_answers(answers)
    assert result.total_points_earned == 40
    assert result.percentage == 40.0
    assert result.passed is False


def test_quiz_runner_rubric_evaluation(quiz_runner: QuizRunner):
    """Verify criterion-based self-evaluation scoring for analysis questions."""
    answers = {}
    mcqs = [q for q in quiz_runner.questions if q["type"] == "mcq"]
    analyses = [q for q in quiz_runner.questions if q["type"] == "analysis"]

    for q in mcqs:
        answers[q["id"]] = q["answer"]  # 60 pts

    # For analysis_1, award full credit (5, 5, 5, 5 = 20 pts)
    # For analysis_2, award partial credit (3, 4, 3, 2 = 12 pts)
    answers[analyses[0]["id"]] = {"c1": 5, "c2": 5, "c3": 5, "c4": 5}
    answers[analyses[1]["id"]] = {"c1": 3, "c2": 4, "c3": 3, "c4": 2}

    result = quiz_runner.evaluate_answers(answers)
    # 60 + 20 + 12 = 92 pts
    assert result.total_points_earned == 92
    assert result.percentage == 92.0
    assert result.passed is True


def test_quiz_runner_automated_tests_method(quiz_runner: QuizRunner):
    """Verify that run_automated_tests completes successfully with no errors."""
    report = quiz_runner.run_automated_tests()
    assert report["success"] is True
    assert report["schema_validation"]["valid"] is True
    assert report["perfect_run_verification"]["points_earned"] == 100
    assert report["deduction_run_verification"]["points_earned"] == 90
    assert len(report["errors"]) == 0


def test_quiz_runner_interactive_simulation(quiz_runner: QuizRunner):
    """Simulate complete interactive run with custom input and output callbacks."""
    # Build simulated inputs:
    # Invalid MCQ input then valid MCQ input for each MCQ
    # Enter for analysis then rubric criterion scores (5, 5, 5, 5)
    mcqs = [q for q in quiz_runner.questions if q["type"] == "mcq"]
    analyses = [q for q in quiz_runner.questions if q["type"] == "analysis"]

    simulated_inputs = []
    for q in mcqs:
        simulated_inputs.append("Z")  # Invalid option triggering re-prompt
        simulated_inputs.append(q["answer"])

    for q in analyses:
        simulated_inputs.append("")  # Press Enter to reveal answer
        criteria = q["rubric"]["criteria"]
        for crit in criteria:
            simulated_inputs.append(str(crit["points"]))  # Full points for criterion

    input_iter = iter(simulated_inputs)
    captured_outputs = []

    def mock_input(prompt: str) -> str:
        return next(input_iter)

    def mock_output(text: str) -> None:
        captured_outputs.append(text)

    result = quiz_runner.run_interactive(input_fn=mock_input, output_fn=mock_output)
    assert result.total_points_earned == 100
    assert result.passed is True

    full_output = "\n".join(captured_outputs)
    assert "Invalid option" in full_output
    assert "EXAMINATION RESULT & TECHNICAL AUDIT REPORT" in full_output
    assert "PASSED" in full_output


def test_quiz_cli_runner_subproc():
    """Verify that quiz_runner.py executed via CLI in --test mode succeeds with returncode 0."""
    res = subprocess.run(
        [sys.executable, "quiz/quiz_runner.py", "--test"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert res.returncode == 0
    assert "AUTOMATED VERIFICATION REPORT" in res.stdout
    assert "PASSED" in res.stdout


def test_quiz_cli_runner_json_subproc():
    """Verify that quiz_runner.py --test --json outputs valid JSON report."""
    res = subprocess.run(
        [sys.executable, "quiz/quiz_runner.py", "--test", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["success"] is True
    assert data["schema_validation"]["valid"] is True
    assert data["perfect_run_verification"]["points_earned"] == 100
