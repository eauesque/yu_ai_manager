"""JSON escape repair helpers."""


def repair_json_backslashes(raw: str) -> str:
    result = []
    i = 0
    in_string = False

    while i < len(raw):
        ch = raw[i]
        if ch == '"':
            if not in_string:
                in_string = True
                result.append(ch)
                i += 1
            else:
                num_bs = 0
                j = len(result) - 1
                while j >= 0 and result[j] == '\\':
                    num_bs += 1
                    j -= 1
                if num_bs % 2 == 0:
                    in_string = False
                    result.append(ch)
                    i += 1
                else:
                    result.append(ch)
                    i += 1
        elif in_string and ch == '\\':
            if i + 1 < len(raw):
                nxt = raw[i + 1]
                if nxt in ('"', '\\', '/', 'b', 'f', 'n', 'r', 't', 'u'):
                    result.append(ch)
                    result.append(nxt)
                    i += 2
                else:
                    result.append('\\')
                    result.append('\\')
                    result.append(nxt)
                    i += 2
            else:
                result.append(ch)
                i += 1
        else:
            result.append(ch)
            i += 1
    return "".join(result)
