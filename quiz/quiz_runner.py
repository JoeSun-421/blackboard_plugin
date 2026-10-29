"""Interactive Technical Quiz Suite & Verification Engine for CUHK Blackboard Plugin.

Provides both an interactive terminal quiz runner with structured self-evaluation rubrics
and an automated test validation engine (--test) verifying data schema, file citations,
and scoring arithmetic.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


DEFAULT_DATA_PATH = Path(__file__).resolve().parent / "quiz_data.json"


def load_quiz_data(data_path: Optional[Path | str] = None) -> Dict[str, Any]:
    """Load and parse the quiz JSON data file."""
    path = Path(data_path) if data_path else DEFAULT_DATA_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Quiz data file not found at: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


@dataclass
class QuestionResult:
    """Stores the evaluation result for a single question."""

    question_id: str
    question_type: str
    category: str
    points_possible: int
    points_earned: int
    user_answer: Any
    correct_answer: Any
    is_correct: bool
    explanation: str
    rubric_feedback: Optional[Dict[str, Any]] = None


@dataclass
class QuizResult:
    """Stores the aggregated results for a complete quiz session."""

    title: str
    total_points_possible: int
    total_points_earned: int
    percentage: float
    passed: bool
    passing_score: int
    category_scores: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    question_results: List[QuestionResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert quiz result to dictionary."""
        return {
            "title": self.title,
            "total_points_possible": self.total_points_possible,
            "total_points_earned": self.total_points_earned,
            "percentage": self.percentage,
            "passed": self.passed,
            "passing_score": self.passing_score,
            "category_scores": self.category_scores,
            "question_results": [
                {
                    "question_id": r.question_id,
                    "question_type": r.question_type,
                    "category": r.category,
                    "points_possible": r.points_possible,
                    "points_earned": r.points_earned,
                    "user_answer": r.user_answer,
                    "correct_answer": r.correct_answer,
                    "is_correct": r.is_correct,
                }
                for r in self.question_results
            ],
        }


class QuizRunner:
    """Engine for running interactive CLI quizzes and automated verification suites."""

    REQUIRED_TOPICS_MCQ = [
        "Architecture & MCP stream isolation",
        "Auth & CDP zero-copy harvesting",
        "Security controls & password exclusion from disk",
        "Dual-engine fallback & SAML ADFS false-positive redirect detection",
        "Core APIs & attachment download path traversal sanitization",
        "Test suite architecture & mock strategies",
    ]

    REQUIRED_TOPICS_ANALYSIS = [
        "Enterprise SSO & Duo 2FA Interception Mitigation",
        "Dual-Engine REST v1 / BeautifulSoup Web Portal Scraper Resilience & Defensive Security",
    ]

    def __init__(self, data_path: Optional[Path | str] = None):
        self.data_path = Path(data_path) if data_path else DEFAULT_DATA_PATH
        self.data = load_quiz_data(self.data_path)
        self.title = self.data.get("title", "CUHK Blackboard Technical Quiz")
        self.total_points = int(self.data.get("total_points", 100))
        self.passing_score = int(self.data.get("passing_score", 70))
        self.questions = self.data.get("questions", [])

    def validate_data(self) -> Tuple[bool, List[str]]:
        """Validate the structural schema and technical requirements of quiz_data.json."""
        errors: List[str] = []

        if not self.questions:
            errors.append("quiz_data.json contains no questions.")
            return False, errors

        mcq_questions = [q for q in self.questions if q.get("type") == "mcq"]
        analysis_questions = [q for q in self.questions if q.get("type") == "analysis"]

        if len(mcq_questions) < 6:
            errors.append(f"Expected at least 6 MCQs, found {len(mcq_questions)}.")

        if len(analysis_questions) < 2:
            errors.append(f"Expected at least 2 Analysis questions, found {len(analysis_questions)}.")

        calc_total = sum(int(q.get("points", 0)) for q in self.questions)
        if calc_total != self.total_points or calc_total != 100:
            errors.append(f"Total points sum to {calc_total}, expected 100.")

        # Validate MCQ fields and options
        for idx, q in enumerate(mcq_questions, 1):
            qid = q.get("id", f"mcq_{idx}")
            if not q.get("category"):
                errors.append(f"MCQ '{qid}' missing category.")
            if not q.get("question"):
                errors.append(f"MCQ '{qid}' missing question text.")
            options = q.get("options", {})
            if not isinstance(options, dict) or set(options.keys()) < {"A", "B", "C", "D"}:
                errors.append(f"MCQ '{qid}' options must include A, B, C, and D.")
            answer = q.get("answer")
            if answer not in options:
                errors.append(f"MCQ '{qid}' answer '{answer}' is not one of the available options.")
            if not q.get("explanation"):
                errors.append(f"MCQ '{qid}' missing explanation.")
            if not q.get("rubric"):
                errors.append(f"MCQ '{qid}' missing rubric.")

        # Validate Analysis questions
        for idx, q in enumerate(analysis_questions, 1):
            qid = q.get("id", f"analysis_{idx}")
            if not q.get("category"):
                errors.append(f"Analysis question '{qid}' missing category.")
            if not q.get("question"):
                errors.append(f"Analysis question '{qid}' missing question text.")
            if not q.get("answer"):
                errors.append(f"Analysis question '{qid}' missing model answer.")
            if not q.get("rubric") or not isinstance(q.get("rubric", {}).get("criteria"), list):
                errors.append(f"Analysis question '{qid}' missing structured rubric with criteria.")
            else:
                criteria = q["rubric"]["criteria"]
                crit_pts = sum(int(c.get("points", 0)) for c in criteria)
                if crit_pts != int(q.get("points", 0)):
                    errors.append(
                        f"Analysis question '{qid}' criteria points sum to {crit_pts}, expected {q.get('points')}."
                    )

        # Validate repository file citations
        repo_root = self.data_path.resolve().parent.parent
        for q in self.questions:
            qid = q.get("id")
            for ref in q.get("code_references", []):
                file_rel = ref.get("file")
                if not file_rel:
                    errors.append(f"Question '{qid}' code reference missing file.")
                    continue
                # Replace slashes for OS cross-compatibility
                target_file = repo_root / file_rel.replace("/", os.sep)
                if not target_file.is_file():
                    errors.append(f"Question '{qid}' cites non-existent file: '{file_rel}'.")

        return (len(errors) == 0), errors

    def evaluate_answers(self, user_answers: Dict[str, Any]) -> QuizResult:
        """Evaluate a dictionary of submitted answers and return a QuizResult."""
        total_earned = 0
        total_possible = 0
        category_map: Dict[str, Dict[str, Any]] = {}
        question_results: List[QuestionResult] = []

        for q in self.questions:
            qid = q["id"]
            qtype = q.get("type", "mcq")
            category = q.get("category", "General")
            points = int(q.get("points", 10))
            explanation = q.get("explanation", "") or q.get("answer", "")

            if category not in category_map:
                category_map[category] = {"earned": 0, "possible": 0, "percentage": 0.0}
            category_map[category]["possible"] += points
            total_possible += points

            user_sub = user_answers.get(qid)

            if qtype == "mcq":
                correct_ans = str(q.get("answer", "")).strip().upper()
                user_ans_str = str(user_sub).strip().upper() if user_sub is not None else ""
                is_correct = user_ans_str == correct_ans
                earned = points if is_correct else 0
                total_earned += earned
                category_map[category]["earned"] += earned

                question_results.append(
                    QuestionResult(
                        question_id=qid,
                        question_type="mcq",
                        category=category,
                        points_possible=points,
                        points_earned=earned,
                        user_answer=user_ans_str,
                        correct_answer=correct_ans,
                        is_correct=is_correct,
                        explanation=explanation,
                    )
                )

            elif qtype == "analysis":
                # For analysis, user_sub can be an integer score or a dict with rubric criteria scores
                earned = 0
                rubric_feedback = {}
                if isinstance(user_sub, dict):
                    # Rubric breakdown dict: {"c1": 5, "c2": 4...}
                    criteria = q.get("rubric", {}).get("criteria", [])
                    for crit in criteria:
                        cid = crit.get("id") or crit.get("criterion")
                        c_max = int(crit.get("points", 5))
                        c_awarded = int(user_sub.get(cid, c_max))
                        c_awarded = max(0, min(c_awarded, c_max))
                        earned += c_awarded
                    rubric_feedback = user_sub
                elif isinstance(user_sub, (int, float)):
                    earned = max(0, min(int(user_sub), points))
                else:
                    earned = points  # Default full credit in automated verification pass

                total_earned += earned
                category_map[category]["earned"] += earned
                is_correct = earned >= (points * 0.7)

                question_results.append(
                    QuestionResult(
                        question_id=qid,
                        question_type="analysis",
                        category=category,
                        points_possible=points,
                        points_earned=earned,
                        user_answer="[Response / Self-Evaluation]",
                        correct_answer=q.get("answer", ""),
                        is_correct=is_correct,
                        explanation=q.get("answer", ""),
                        rubric_feedback=rubric_feedback,
                    )
                )

        # Compute percentages
        for cat in category_map.values():
            if cat["possible"] > 0:
                cat["percentage"] = round((cat["earned"] / cat["possible"]) * 100, 2)

        overall_pct = round((total_earned / total_possible) * 100, 2) if total_possible > 0 else 0.0
        passed = total_earned >= self.passing_score

        return QuizResult(
            title=self.title,
            total_points_possible=total_possible,
            total_points_earned=total_earned,
            percentage=overall_pct,
            passed=passed,
            passing_score=self.passing_score,
            category_scores=category_map,
            question_results=question_results,
        )

    def run_automated_tests(self) -> Dict[str, Any]:
        """Execute automated test verification suite (--test).
        
        Validates schema, citations, simulated perfect score, deduction arithmetic,
        and category breakdowns. Returns a comprehensive report.
        """
        report: Dict[str, Any] = {
            "success": True,
            "schema_validation": {},
            "perfect_run_verification": {},
            "deduction_run_verification": {},
            "category_verification": {},
            "errors": [],
        }

        # 1. Schema & citation validation
        is_valid, errors = self.validate_data()
        report["schema_validation"] = {
            "valid": is_valid,
            "total_questions": len(self.questions),
            "mcq_count": len([q for q in self.questions if q.get("type") == "mcq"]),
            "analysis_count": len([q for q in self.questions if q.get("type") == "analysis"]),
            "errors": errors,
        }
        if not is_valid:
            report["success"] = False
            report["errors"].extend(errors)
            return report

        # 2. Perfect score run simulation
        perfect_answers: Dict[str, Any] = {}
        for q in self.questions:
            if q.get("type") == "mcq":
                perfect_answers[q["id"]] = q["answer"]
            else:
                perfect_answers[q["id"]] = q["points"]

        res_perfect = self.evaluate_answers(perfect_answers)
        if res_perfect.total_points_earned != 100 or res_perfect.percentage != 100.0 or not res_perfect.passed:
            err = f"Perfect run failed: earned {res_perfect.total_points_earned}/100, expected 100/100."
            report["success"] = False
            report["errors"].append(err)

        report["perfect_run_verification"] = {
            "points_earned": res_perfect.total_points_earned,
            "percentage": res_perfect.percentage,
            "passed": res_perfect.passed,
        }

        # 3. Simulated deduction run (get first MCQ wrong)
        deduction_answers = dict(perfect_answers)
        first_mcq = next(q for q in self.questions if q.get("type") == "mcq")
        correct_opt = first_mcq["answer"]
        wrong_opt = "A" if correct_opt != "A" else "B"
        deduction_answers[first_mcq["id"]] = wrong_opt

        res_deduction = self.evaluate_answers(deduction_answers)
        expected_pts = 100 - int(first_mcq["points"])
        expected_pct = round((expected_pts / 100.0) * 100, 2)
        if res_deduction.total_points_earned != expected_pts or res_deduction.percentage != expected_pct:
            err = (
                f"Deduction run failed: earned {res_deduction.total_points_earned}, expected {expected_pts}."
            )
            report["success"] = False
            report["errors"].append(err)

        report["deduction_run_verification"] = {
            "deducted_question": first_mcq["id"],
            "points_earned": res_deduction.total_points_earned,
            "percentage": res_deduction.percentage,
            "passed": res_deduction.passed,
        }

        # 4. Category breakdown verification
        categories = set(q.get("category") for q in self.questions)
        for cat in categories:
            if cat not in res_perfect.category_scores:
                err = f"Category '{cat}' missing from category scores breakdown."
                report["success"] = False
                report["errors"].append(err)
            else:
                c_data = res_perfect.category_scores[cat]
                if c_data["earned"] != c_data["possible"] or c_data["percentage"] != 100.0:
                    err = f"Category '{cat}' perfect score mismatch: {c_data}."
                    report["success"] = False
                    report["errors"].append(err)

        report["category_verification"] = {
            "categories_tested": list(categories),
            "breakdown": res_perfect.category_scores,
        }

        return report

    def run_interactive(
        self,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ) -> QuizResult:
        """Run the interactive command-line technical examination."""
        output_fn("\n" + "=" * 76)
        output_fn(f"🎓 {self.title}")
        output_fn("=" * 76)
        output_fn(f"System Version: {self.data.get('version', '1.0.0')}")
        output_fn(f"Total Points: {self.total_points} pts | Passing Threshold: {self.passing_score} pts (70%)")
        output_fn(f"Structure: {len(self.questions)} Deep Technical Questions (MCQs & Scenario Analyses)")
        output_fn("=" * 76 + "\n")

        user_answers: Dict[str, Any] = {}
        mcqs = [q for q in self.questions if q.get("type") == "mcq"]
        analyses = [q for q in self.questions if q.get("type") == "analysis"]

        # Part 1: Multiple Choice Questions
        output_fn("📋 PART I: MULTIPLE-CHOICE QUESTIONS (60 Points Total)")
        output_fn("-" * 76)

        for idx, q in enumerate(mcqs, 1):
            qid = q["id"]
            pts = q.get("points", 10)
            cat = q.get("category", "")
            output_fn(f"\n[Question {idx}/{len(mcqs)}] ({pts} pts) Category: {cat}")
            output_fn(f"{q['question']}\n")

            options = q.get("options", {})
            for key in sorted(options.keys()):
                output_fn(f"  [{key}] {options[key]}")

            while True:
                choice = input_fn("\nYour Answer [A/B/C/D]: ").strip().upper()
                if choice in options:
                    break
                output_fn("❌ Invalid option. Please enter A, B, C, or D.")

            user_answers[qid] = choice
            correct = choice == q["answer"]

            if correct:
                output_fn(f"✅ CORRECT! (+{pts} points)")
            else:
                output_fn(f"❌ INCORRECT. Correct Answer: [{q['answer']}]")

            output_fn(f"\n💡 Technical Explanation:\n{q.get('explanation')}")
            for ref in q.get("code_references", []):
                output_fn(f"   📂 Code Citation: {ref.get('file')} (lines {ref.get('lines')})")
            output_fn("-" * 76)

        # Part 2: Comprehensive Technical Analysis Questions
        output_fn("\n\n🔬 PART II: COMPREHENSIVE TECHNICAL ANALYSIS QUESTIONS (40 Points Total)")
        output_fn("-" * 76)

        for idx, q in enumerate(analyses, 1):
            qid = q["id"]
            pts = q.get("points", 20)
            cat = q.get("category", "")
            output_fn(f"\n[Analysis {idx}/{len(analyses)}] ({pts} pts) Category: {cat}")
            output_fn(f"{q['question']}\n")

            output_fn("📝 Please synthesize your technical analysis in your console or editor.")
            input_fn("Press [Enter] when ready to reveal the authoritative model answer & scoring rubric: ")

            output_fn("\n" + "=" * 76)
            output_fn("🏛️ AUTHORITATIVE ARCHITECTURAL MODEL ANSWER:")
            output_fn("=" * 76)
            output_fn(q.get("answer", ""))
            output_fn("\n📂 Code References:")
            for ref in q.get("code_references", []):
                output_fn(f"  - {ref.get('file')} ({ref.get('lines')}): {ref.get('description')}")

            # Interactive Self-Evaluation Rubric
            output_fn("\n" + "-" * 76)
            output_fn("📊 STRUCTURED SELF-EVALUATION RUBRIC:")
            rubric = q.get("rubric", {})
            criteria = rubric.get("criteria", [])
            rubric_scores: Dict[str, int] = {}
            total_awarded = 0

            for c_idx, crit in enumerate(criteria, 1):
                cid = crit.get("id") or f"c{c_idx}"
                c_title = crit.get("criterion", f"Criterion {c_idx}")
                c_max = int(crit.get("points", 5))
                c_desc = crit.get("description", "")

                output_fn(f"\n  Criterion {c_idx}: {c_title} (Max: {c_max} pts)")
                output_fn(f"  Standard: {c_desc}")

                while True:
                    prompt_str = f"  Awarded Points for Criterion {c_idx} [0-{c_max}]: "
                    val_str = input_fn(prompt_str).strip()
                    try:
                        pts_awarded = int(val_str)
                        if 0 <= pts_awarded <= c_max:
                            rubric_scores[cid] = pts_awarded
                            total_awarded += pts_awarded
                            break
                        output_fn(f"  ❌ Points must be between 0 and {c_max}.")
                    except ValueError:
                        output_fn("  ❌ Please enter a valid integer.")

            user_answers[qid] = rubric_scores
            output_fn(f"\nTotal Awarded for Analysis {idx}: {total_awarded} / {pts} points")
            output_fn("-" * 76)

        # Final Evaluation
        result = self.evaluate_answers(user_answers)
        self._display_final_report(result, output_fn)
        return result

    def _display_final_report(self, result: QuizResult, output_fn: Callable[[str], None] = print) -> None:
        """Display the formatted final grading report."""
        output_fn("\n" + "=" * 76)
        output_fn("🏁 EXAMINATION RESULT & TECHNICAL AUDIT REPORT")
        output_fn("=" * 76)
        output_fn(f"Total Score:       {result.total_points_earned} / {result.total_points_possible}")
        output_fn(f"Score Percentage:  {result.percentage:.1f}%")
        status_str = "🎉 PASSED (Certified CUHK Blackboard Plugin Architect)" if result.passed else "⚠️ FAILED (Needs Review)"
        output_fn(f"Status:            {status_str}")
        output_fn("-" * 76)
        output_fn("📊 CATEGORY-BY-CATEGORY BREAKDOWN:")
        output_fn(f"{'Category':<45} | {'Earned':<7} | {'Possible':<8} | {'Yield':<6}")
        output_fn("-" * 76)
        for cat_name, stats in result.category_scores.items():
            output_fn(
                f"{cat_name:<45} | {stats['earned']:<7} | {stats['possible']:<8} | {stats['percentage']:>5.1f}%"
            )
        output_fn("=" * 76)
        if result.passed:
            output_fn("🌟 Excellent mastery of MCP protocols, auth engineering, and defensive LMS scraping!")
        else:
            output_fn("💡 Recommended Action: Review ARCHITECTURE_REVIEW.md sections corresponding to failed topics.")
        output_fn("=" * 76 + "\n")


def run_cli() -> int:
    """CLI entry point for quiz runner supporting interactive and automated modes."""
    parser = argparse.ArgumentParser(
        description="CUHK Blackboard Plugin Interactive Technical Quiz Suite & Runner"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run automated schema, citation, and scoring arithmetic verification tests and exit.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output automated test report as formatted JSON.",
    )
    parser.add_argument(
        "--data",
        type=str,
        default=None,
        help="Custom path to quiz_data.json.",
    )

    args = parser.parse_args()
    runner = QuizRunner(data_path=args.data)

    if args.test:
        report = runner.run_automated_tests()
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print("\n" + "=" * 76)
            print("🧪 CUHK BLACKBOARD QUIZ ENGINE AUTOMATED VERIFICATION REPORT")
            print("=" * 76)
            print(f"Overall Status:            {'✅ PASSED' if report['success'] else '❌ FAILED'}")
            print(f"Schema Validation:         {'✅ Valid' if report['schema_validation'].get('valid') else '❌ Invalid'}")
            print(f"Total Questions Verified:  {report['schema_validation'].get('total_questions')}")
            print(f"MCQ Questions Count:       {report['schema_validation'].get('mcq_count')} (Expected >= 6)")
            print(f"Analysis Questions Count:  {report['schema_validation'].get('analysis_count')} (Expected >= 2)")
            print(f"Perfect Run Simulation:    {report['perfect_run_verification'].get('points_earned')}/100 pts (100.0%)")
            print(f"Deduction Run Simulation:  {report['deduction_run_verification'].get('points_earned')}/100 pts")
            print(f"Categories Audited:        {len(report['category_verification'].get('categories_tested', []))}")
            if report["errors"]:
                print("\n❌ Errors Encountered:")
                for err in report["errors"]:
                    print(f"  - {err}")
            print("=" * 76)

        return 0 if report["success"] else 1
    else:
        runner.run_interactive()
        return 0


def main():
    """Main execution function."""
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
