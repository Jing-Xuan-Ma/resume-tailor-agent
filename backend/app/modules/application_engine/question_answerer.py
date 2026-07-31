from pathlib import Path

from app.modules.application_engine.option_matcher import best_option


class QuestionAnswerer:
    def answer(
        self,
        *,
        question: str,
        field_type: str,
        options: list[str] | None,
        user_profile: dict,
        job: dict,
        field_name: str = "",
        artifacts: dict | None = None,
    ) -> dict:
        q = question.lower()
        name = (field_name or "").lower()
        profile = user_profile or {}
        artifacts = artifacts or {}
        answer = ""
        confidence = 0.5

        if name == "first_name" or "first name" in q:
            answer = str(profile.get("first_name") or self._split_name(profile).get("first_name") or "")
            confidence = 0.9 if answer else 0.2
        elif name == "last_name" or "last name" in q:
            answer = str(profile.get("last_name") or self._split_name(profile).get("last_name") or "")
            confidence = 0.9 if answer else 0.2
        elif name in {"full_name", "name"} or "full name" in q or q.strip() in {"name", "legal name"}:
            answer = str(profile.get("full_name") or profile.get("name") or "")
            if not answer:
                parts = [self._split_name(profile).get("first_name"), self._split_name(profile).get("last_name")]
                answer = " ".join(part for part in parts if part).strip()
            confidence = 0.9 if answer else 0.2
        elif name == "email" or "email" in q or "e-mail" in q:
            answer = str(profile.get("email") or "")
            confidence = 0.9 if answer else 0.2
        elif name == "phone" or any(token in q for token in ("phone", "mobile", "telephone", "tel")):
            answer = str(profile.get("phone") or profile.get("mobile") or profile.get("telephone") or "")
            confidence = 0.9 if answer else 0.2
        elif name == "org" or "current company" in q or q.strip() in {"company", "organization", "employer"}:
            answer = str(profile.get("current_company") or profile.get("company") or profile.get("org") or "")
            confidence = 0.8 if answer else 0.2
        elif name == "linkedin" or "linkedin" in q:
            answer = str(profile.get("linkedin_url") or profile.get("linkedin") or "")
            confidence = 0.8 if answer else 0.2
        elif name == "website" or "website" in q or "portfolio" in q:
            answer = str(profile.get("portfolio_url") or profile.get("website") or "")
            confidence = 0.8 if answer else 0.2
        elif name == "github" or "github" in q:
            answer = str(profile.get("github_url") or profile.get("github") or "")
            confidence = 0.8 if answer else 0.2
        elif name == "twitter" or "twitter" in q or "x profile" in q:
            answer = str(profile.get("twitter_url") or profile.get("twitter") or profile.get("x_url") or "")
            confidence = 0.7 if answer else 0.2
        elif "authorized" in q or "work authorization" in q or name == "work_authorization":
            answer = "Yes" if profile.get("work_authorized", True) else "No"
            confidence = 0.7
        elif "source" in q or "hear about" in q:
            answer = "LinkedIn" if "linkedin" in str(job.get("source_platform", "")).lower() else "Company Website"
            confidence = 0.6
        elif name == "cover_letter" or "cover letter" in q or "additional information" in q:
            # Prefer cover letter text for Lever textareas; fall back to artifact path.
            text = ""
            path = artifacts.get("cover_letter")
            if path:
                try:
                    text = Path(str(path)).read_text(encoding="utf-8").strip()
                except Exception:
                    text = ""
            if field_type == "file":
                answer = str(path or "")
                confidence = 1.0 if answer else 0.2
            else:
                answer = text or str(profile.get("cover_letter") or "")
                if not answer and path:
                    answer = str(path)
                confidence = 0.9 if answer else 0.2
        elif field_type == "file":
            answer = str(artifacts.get(name) or artifacts.get(field_name) or "")
            confidence = 1.0 if answer else 0.2
        else:
            answer = "Needs manual review"
            confidence = 0.1

        matched = best_option(answer, options or []) if options else answer
        return {
            "question": question,
            "answer": matched,
            "confidence": confidence,
            "requires_review": confidence < 0.75,
        }

    def _split_name(self, profile: dict) -> dict[str, str]:
        full_name = str(profile.get("full_name") or profile.get("name") or "").strip()
        if not full_name:
            return {"first_name": "", "last_name": ""}
        parts = full_name.split()
        return {"first_name": parts[0], "last_name": " ".join(parts[1:]) if len(parts) > 1 else ""}
