"""Prompt splitting helpers."""


from core.helpers_core.helpers_text_path import norm_space


def smart_split_by_comma(text: str) -> list[str]:
    result = []
    current = []
    paren_depth = 0
    brace_depth = 0
    angle_depth = 0

    for char in text:
        if char == "(":
            paren_depth += 1
            current.append(char)
        elif char == ")":
            paren_depth = max(0, paren_depth - 1)
            current.append(char)
        elif char == "{":
            brace_depth += 1
            current.append(char)
        elif char == "}":
            brace_depth = max(0, brace_depth - 1)
            current.append(char)
        elif char == "<":
            angle_depth += 1
            current.append(char)
        elif char == ">":
            angle_depth = max(0, angle_depth - 1)
            current.append(char)
        elif char == "," and paren_depth == 0 and brace_depth == 0 and angle_depth == 0:
            result.append("".join(current))
            current = []
        else:
            current.append(char)

    if current:
        result.append("".join(current))

    return [norm_space(x) for x in result if norm_space(x)]
