def classify_grade(cps: float) -> str:
    if cps >= 80:
        return "A"
    if cps >= 60:
        return "B"
    if cps >= 40:
        return "C"
    return "D"


def classify_performance_label(cps: float) -> str:
    grade = classify_grade(cps)
    if grade == "A":
        return "high_performer"
    if grade == "B":
        return "strong_performer"
    if grade == "C":
        return "average_performer"
    return "low_performer"
