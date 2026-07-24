from app.modules.application_engine.option_matcher import best_option


class QuestionAnswerer:
    def answer(self, *, question: str, field_type: str, options: list[str] | None, user_profile: dict, job: dict, field_name: str = "", artifacts: dict | None = None) -> dict:
        q = question.lower()
        profile = user_profile or {}
        artifacts = artifacts or {}
        answer = ""
        confidence = 0.5

        if field_name == "first_name" or "first name" in q:
            answer = str(profile.get("first_name") or self._split_name(profile).get("first_name") or "")
            confidence = 0.9 if answer else 0.2
        elif field_name == "last_name" or "last name" in q:
            answer = str(profile.get("last_name") or self._split_name(profile).get("last_name") or "")
            confidence = 0.9 if answer else 0.2
        elif "email" in q:
            answer = str(profile.get("email") or "")
            confidence = 0.9 if answer else 0.2
        elif "full name" in q or "name" == q.strip():
            answer = str(profile.get("full_name") or profile.get("name") or "")
            confidence = 0.9 if answer else 0.2
        elif "linkedin" in q:
            answer = str(profile.get("linkedin_url") or "")
            confidence = 0.8 if answer else 0.2
        elif "website" in q or "portfolio" in q:
            answer = str(profile.get("portfolio_url") or "")
            confidence = 0.8 if answer else 0.2
        elif "authorized" in q or "work authorization" in q:
            answer = "Yes" if profile.get("work_authorized", True) else "No"
            confidence = 0.7
        elif "source" in q or "hear about" in q:
            answer = "LinkedIn" if "linkedin" in str(job.get("source_platform", "")).lower() else "Company Website"
            confidence = 0.6
        elif field_type == "file":
            answer = str(artifacts.get(field_name) or "")
            confidence = 1.0 if answer else 0.2
        else:
            answer = "Needs manual review"
            confidence = 0.1

        matched = best_option(answer, options or []) if options else answer
        return {"question": question, "answer": matched, "confidence": confidence, "requires_review": confidence < 0.75}

    def _split_name(self, profile: dict) -> dict[str, str]:
        full_name = str(profile.get("full_name") or profile.get("name") or "").strip()
        if not full_name:
            return {"first_name": "", "last_name": ""}
        parts = full_name.split()
        return {"first_name": parts[0], "last_name": " ".join(parts[1:]) if len(parts) > 1 else ""}
