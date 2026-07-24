from difflib import SequenceMatcher


def best_option(answer: str, options: list[str]) -> str:
    if not options:
        return answer
    answer_lower = answer.lower().strip()
    return max(options, key=lambda option: SequenceMatcher(None, answer_lower, option.lower()).ratio())
