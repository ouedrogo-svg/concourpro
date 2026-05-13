import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class QuizRow:
    question: str
    reponse: str
    propositions: Tuple[Tuple[str, str], ...] = ()


def _norm(s: str) -> str:
    s = (s or "").replace("\n", " ").replace("\r", " ")
    return re.sub(r"\s+", " ", s.strip()).lower()


def _clean_cell(s: Optional[str]) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _is_questions_column_norm(h: str) -> bool:
    if not h:
        return False
    h = h.replace("é", "e").replace("è", "e").replace("ê", "e").replace("ë", "e")
    if h in {"questions", "question", "q", "intitule", "libelle"}:
        return True
    if "question" in h and "repons" not in h:
        return True
    return False


def _is_reponses_column_norm(h: str) -> bool:
    """Colonne unique des bonnes reponses (pas 'reponse a' = choix A)."""
    if not h:
        return False
    h = h.replace("é", "e").replace("è", "e").replace("ê", "e").replace("ë", "e")
    if re.match(r"^reponse\s+[a-z]\b", h):
        return False
    if h in {
        "reponses",
        "reponse",
        "answers",
        "answer",
        "corrige",
        "correct",
        "solution",
        "solutions",
    }:
        return True
    if "reponse" in h and "question" not in h:
        return True
    if "repons" in h:
        return True
    if h.startswith("bonne reponse") or h.startswith("bonnes reponses"):
        return True
    # En-tete abime (PDF) : "rponses", "ponses" sans le e initial
    if h.endswith("ponses") and "question" not in h and "proposition" not in h:
        return True
    return False


def _header_choice_letter(cell: Optional[str]) -> Optional[str]:
    """Retourne A..Z si l'en-tete designe une colonne de proposition (A, Proposition B, etc.)."""
    raw = _clean_cell(cell)
    if not raw:
        return None
    t = _norm(raw)
    t = t.replace("é", "e").replace("è", "e")
    if _is_reponses_column_norm(t) or _is_questions_column_norm(t):
        return None
    if len(t) == 1 and "a" <= t <= "z":
        return t.upper()
    m = re.match(r"^proposition\s+([a-z])\s*$", t)
    if m:
        return m.group(1).upper()
    m = re.match(r"^propositions\s+([a-z])\s*$", t)
    if m:
        return m.group(1).upper()
    m = re.match(r"^choix\s+([a-z])\s*$", t)
    if m:
        return m.group(1).upper()
    m = re.match(r"^options?\s+([a-z])\s*$", t)
    if m:
        return m.group(1).upper()
    m = re.match(r"^reponse\s+([a-z])\s*$", t)
    if m:
        return m.group(1).upper()
    m = re.match(r"^([a-z])\s*[\.)]\s*$", t)
    if m:
        return m.group(1).upper()
    return None


def _choice_column_indices(
    header_cells: List[str], idx_q: Optional[int], idx_r: Optional[int]
) -> List[Tuple[str, int]]:
    seen: set[str] = set()
    out: List[Tuple[str, int]] = []
    for i, cell in enumerate(header_cells):
        if idx_q is not None and i == idx_q:
            continue
        if idx_r is not None and i == idx_r:
            continue
        hn = _norm(_clean_cell(cell))
        if _is_reponses_column_norm(hn) or _is_questions_column_norm(hn):
            continue
        letter = _header_choice_letter(cell)
        if letter and letter not in seen:
            seen.add(letter)
            out.append((letter, i))
    out.sort(key=lambda x: x[1])
    return out


def _row_cells(raw: List[Optional[str]], n: int) -> List[str]:
    out: List[str] = []
    for i in range(n):
        c = raw[i] if i < len(raw) else None
        out.append(_clean_cell(c))
    return out


def _find_ordre_column(header_norm: List[str]) -> int:
    for i, h in enumerate(header_norm):
        if not h:
            continue
        if "ordre" in h:
            return i
        if re.match(r"^n\s*[`'´]?\s*d\s*ordre", h):
            return i
        if h in {"n", "no", "numero", "n°", "n "}:  # rare
            return i
    return 0


def _detect_question_body_column(
    table: List[List[Optional[str]]],
    idx_ordre: int,
    idx_r: Optional[int],
    idx_q: Optional[int],
    ncols: int,
    data_start_row: int = 1,
) -> int:
    """Colonne ou le libelle de question est le plus souvent rempli (souvent a droite de 'Questions')."""
    scores = [0] * ncols
    lo = data_start_row
    hi = min(lo + 40, len(table))
    for raw in table[lo:hi]:
        if not raw:
            continue
        cells = _row_cells(raw, ncols)
        for i in range(ncols):
            if i == idx_ordre or i == idx_r:
                continue
            scores[i] += len(cells[i])
    best = max(range(ncols), key=lambda i: scores[i])
    if scores[best] < 12 and idx_q is not None and 0 <= idx_q < ncols:
        return idx_q
    return best


def _split_stem_and_inline_propositions(
    text: str,
) -> Tuple[str, Tuple[Tuple[str, str], ...]]:
    """Decoupe 'A) ...' / 'A. ...' en propositions ; le reste forme l'enonce."""
    if not text or not text.strip():
        return "", ()
    props: List[Tuple[str, str]] = []
    stem_lines: List[str] = []
    pat_paren = re.compile(r"^\s*([A-Z])\)\s*(.+?)\s*$", re.IGNORECASE)
    pat_dot = re.compile(r"^\s*([A-Z])\.\s+(.+?)\s*$", re.IGNORECASE)
    for line in text.splitlines():
        line_n = line.strip()
        if not line_n:
            continue
        m = pat_paren.match(line_n) or pat_dot.match(line_n)
        if m:
            props.append((m.group(1).upper(), m.group(2).strip()))
        else:
            stem_lines.append(line_n)
    stem = " ".join(stem_lines).strip()
    return stem, tuple(props)


def _strip_inline_proposition_lines(text: str) -> str:
    lines_out: List[str] = []
    for line in text.splitlines():
        line_n = line.strip()
        if not line_n:
            continue
        if re.match(r"^\s*[A-Z]\)\s*", line_n, re.IGNORECASE):
            continue
        if re.match(r"^\s*[A-Z]\.\s+", line_n, re.IGNORECASE):
            continue
        lines_out.append(line_n)
    return " ".join(lines_out).strip()


def _merge_reponse_parts(parts: List[str]) -> str:
    cleaned = [_clean_cell(p) for p in parts if _clean_cell(p)]
    if not cleaned:
        return ""
    for p in reversed(cleaned):
        u = p.strip().upper().replace(" ", "")
        if re.fullmatch(r"[A-Z]{1,6}", u):
            return u
    return cleaned[-1].strip()


def _rows_from_questions_reponses_table(
    table: List[List[Optional[str]]],
    header: List[str],
    header_norm: List[str],
    idx_q: Optional[int],
    idx_r: int,
    carry: List[str],
    prior_rows: List[QuizRow],
    data_start_row: int = 1,
) -> List[QuizRow]:
    idx_ordre = _find_ordre_column(header_norm)
    ncols = max(len(header), max((len(r or []) for r in table), default=0))
    idx_body = _detect_question_body_column(
        table, idx_ordre, idx_r, idx_q, ncols, data_start_row=data_start_row
    )
    choice_idx = _choice_column_indices(header, idx_q, idx_r)

    q_parts: List[str] = []
    r_parts: List[str] = []
    first_row_cells: Optional[List[str]] = None
    cur_ordre: Optional[str] = None
    rows_out: List[QuizRow] = []

    def flush() -> None:
        nonlocal q_parts, r_parts, first_row_cells, cur_ordre
        if cur_ordre is None:
            return
        merged_q = "\n".join(q_parts).strip()
        merged_r = _merge_reponse_parts(r_parts)
        if not merged_q or not merged_r:
            q_parts, r_parts, first_row_cells, cur_ordre = [], [], None, None
            return
        props_col: List[Tuple[str, str]] = []
        if first_row_cells and choice_idx:
            for letter, ci in choice_idx:
                if ci < len(first_row_cells) and first_row_cells[ci]:
                    props_col.append((letter, first_row_cells[ci]))
        stem, props_inline = _split_stem_and_inline_propositions(merged_q)
        if props_col:
            question = _strip_inline_proposition_lines(merged_q) or stem or merged_q
            props_final: Tuple[Tuple[str, str], ...] = tuple(props_col)
        else:
            question = stem or merged_q
            props_final = props_inline
        rows_out.append(
            QuizRow(question=question, reponse=merged_r, propositions=props_final)
        )
        q_parts, r_parts, first_row_cells, cur_ordre = [], [], None, None

    for raw in table[data_start_row:]:
        if not raw:
            continue
        cells = _row_cells(raw, ncols)
        ordre_cell = cells[idx_ordre] if idx_ordre < len(cells) else ""
        q_here = cells[idx_body] if idx_body < len(cells) else ""
        if (
            idx_q is not None
            and idx_q != idx_body
            and idx_q < len(cells)
            and cells[idx_q]
        ):
            q_here = (q_here + "\n" + cells[idx_q]).strip() if q_here else cells[idx_q]
        r_here = cells[idx_r] if idx_r < len(cells) else ""

        if ordre_cell and _norm(ordre_cell) in {"n d ordre", "ordre", "questions", "reponses"}:
            continue

        if ordre_cell and ordre_cell != cur_ordre:
            flush()
            cur_ordre = ordre_cell
            first_row_cells = list(cells)
            if carry and not rows_out and prior_rows:
                _merge_carry_into_last_row(prior_rows, carry)

        if cur_ordre is None:
            if not ordre_cell and q_here:
                carry.append(q_here)
            continue

        if q_here:
            q_parts.append(q_here)
        if r_here:
            r_parts.append(r_here)
    flush()
    return rows_out


def _first_row_looks_like_continuation(cells: List[str]) -> bool:
    """Tableau sans en-tete : 1re ligne = suite d'une question (souvent 'C) ...')."""
    if not cells or len(cells) < 3:
        return False
    if cells[0].strip():
        return False
    t = (cells[2] if len(cells) > 2 else "").strip()
    if re.match(r"^\s*[A-Z]\)\s*", t, re.IGNORECASE):
        return True
    if re.match(r"^\s*[A-Z]\.\s+", t, re.IGNORECASE):
        return True
    return False


def _merge_carry_into_last_row(rows: List[QuizRow], carry: List[str]) -> None:
    """Ajoute des lignes de suite (souvent C) D) en tete de page) a la derniere question."""
    if not rows or not carry:
        carry.clear()
        return
    idx = len(rows) - 1
    last = rows[idx]
    merged_q = (last.question + "\n" + "\n".join(carry)).strip()
    carry.clear()
    stem, props_add = _split_stem_and_inline_propositions(merged_q)
    by_letter: dict[str, str] = {L: t for L, t in last.propositions}
    for L, t in props_add:
        by_letter[L] = t
    ordered = tuple(sorted(by_letter.items(), key=lambda x: x[0]))
    rows[idx] = QuizRow(
        question=stem or merged_q,
        reponse=last.reponse,
        propositions=ordered,
    )


def _iter_rows_from_table(
    table: List[List[Optional[str]]], carry: List[str], prior_rows: List[QuizRow]
) -> List[QuizRow]:
    if not table:
        return []

    header_raw = table[0] or []
    header = [_clean_cell(c) for c in header_raw]
    header_norm = [_norm(c) for c in header]

    idx_q = next(
        (i for i, h in enumerate(header_norm) if _is_questions_column_norm(h)), None
    )
    idx_r = next(
        (i for i, h in enumerate(header_norm) if _is_reponses_column_norm(h)), None
    )

    if idx_r is not None:
        return _rows_from_questions_reponses_table(
            table, header, header_norm, idx_q, idx_r, carry, prior_rows, data_start_row=1
        )

    header_raw = table[0] or []
    ncols0 = len(header_raw)
    cells0 = _row_cells(header_raw, ncols0)
    if (
        prior_rows
        and ncols0 >= 4
        and _first_row_looks_like_continuation(cells0)
    ):
        synth_header = ["Ordre", "Questions", "", "", "Réponses"]
        synth_norm = [_norm(h) for h in synth_header]
        return _rows_from_questions_reponses_table(
            table,
            synth_header,
            synth_norm,
            1,
            4,
            carry,
            prior_rows,
            data_start_row=0,
        )

    # Fallback: 2 premieres colonnes = question + reponse, sans propositions structurees.
    rows_fallback: List[QuizRow] = []
    for raw in table:
        if not raw:
            continue
        cleaned = [_clean_cell(c) for c in raw if _clean_cell(c)]
        if len(cleaned) < 2:
            continue
        q = cleaned[0]
        r = cleaned[1]
        if _norm(q) in {"question", "questions"} and _norm(r) in {
            "reponse",
            "reponses",
            "answer",
            "answers",
        }:
            continue
        extra_props: List[Tuple[str, str]] = []
        if len(cleaned) >= 3:
            for j, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
                ci = 2 + j
                if ci >= len(cleaned):
                    break
                txt = cleaned[ci]
                if txt:
                    extra_props.append((letter, txt))
        rows_fallback.append(
            QuizRow(
                question=q,
                reponse=r,
                propositions=tuple(extra_props),
            )
        )
    return rows_fallback


def _extract_from_ift_correction_text(full_text: str) -> List[QuizRow]:
    """
    Repli si extract_tables() ne renvoie rien : parse le flux texte des corrections IFT
    (questions avec '?', options A) B)... , numeros d'ordre / reponses variables).
    """
    text = (full_text or "").replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = text.split("\n")
    lines: List[str] = []
    for ln in raw_lines:
        s = ln.strip()
        if not s:
            continue
        if re.match(r"^\*+$", s):
            continue
        if "Innovation_Formation" in s and "contact_" in s:
            continue
        lines.append(s)

    i0 = 0
    for j, ln in enumerate(lines):
        low = ln.lower()
        if re.search(r"d['\u2019]?\s*ordre\s*$", low) or re.match(
            r"^n\s*['\u2019]?\s*d\s*['\u2019]?\s*ordre\s*$", low
        ):
            i0 = j + 1
            break
        if "questions" in low and "repons" in low.replace("é", "e"):
            i0 = j + 1

    re_opt = re.compile(r"^([A-Z])\)\s*(.*)$")
    re_ord_opt = re.compile(r"^(\d+)\s+([A-Z])\)\s+(.*)$")
    re_ord_only = re.compile(r"^(\d+)\s+([A-Z]{1,6})\s*$")

    rows_out: List[QuizRow] = []
    i = i0
    while i < len(lines):
        while i < len(lines) and lines[i].startswith("NB"):
            i += 1
        if i >= len(lines):
            break

        q_lines: List[str] = []
        while i < len(lines):
            ln = lines[i]
            if ln.startswith("NB"):
                break
            if re_opt.match(ln):
                break
            if re_ord_only.match(ln) and i + 1 < len(lines) and re_opt.match(lines[i + 1]):
                break
            q_lines.append(ln)
            i += 1

        answer_prefix = ""
        if i < len(lines) and re_ord_only.match(lines[i]) and i + 1 < len(lines) and re_opt.match(
            lines[i + 1]
        ):
            answer_prefix = re_ord_only.match(lines[i]).group(2).upper()
            i += 1

        if not q_lines:
            i += 1
            continue

        question = "\n".join(q_lines).strip()
        props: dict[str, str] = {}
        answer_tail = ""

        while i < len(lines):
            ln = lines[i]
            if ln.startswith("NB"):
                break
            moo = re_ord_opt.match(ln)
            if moo:
                letter = moo.group(2).upper()
                rest = moo.group(3).strip()
                tail_m = re.search(r"\s+([A-D])\s*$", rest, re.I)
                if tail_m and tail_m.start() >= 8:
                    prop_body = rest[: tail_m.start()].rstrip()
                    answer_tail += tail_m.group(1).upper()
                else:
                    prop_body = rest
                props[letter] = prop_body.strip()
                i += 1
                continue
            m_stand = re_ord_only.match(ln)
            if m_stand:
                answer_tail += m_stand.group(2).upper()
                i += 1
                continue
            mo3 = re_opt.match(ln)
            if mo3:
                props[mo3.group(1).upper()] = mo3.group(2).strip()
                i += 1
                continue
            break

        while i < len(lines) and lines[i].startswith("NB"):
            i += 1

        merged_answer = (answer_prefix + answer_tail).strip()
        merged_answer = "".join(sorted(set(merged_answer))) if merged_answer else ""
        if not question or not merged_answer or len(props) < 2:
            continue
        ordered_props = tuple(sorted(props.items(), key=lambda x: x[0]))
        rows_out.append(
            QuizRow(question=question, reponse=merged_answer, propositions=ordered_props)
        )

    return rows_out


def _iter_rows_from_text(text: str) -> Iterable[QuizRow]:
    """
    Fallback si la table n'est pas detectee. Accepte des lignes du style:
    - question | reponse
    - question ; reponse
    - question -> reponse
    """
    if not text:
        return []
    candidates: List[QuizRow] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) < 5:
            continue
        if _norm(line) in {"question reponses", "questions reponses"}:
            continue

        m = re.split(r"\s*(\||;|->|—|-{2,}|:)\s*", line, maxsplit=1)
        if len(m) >= 3:
            left = _clean_cell(m[0])
            right = _clean_cell("".join(m[2:]))
            if left and right:
                candidates.append(QuizRow(question=left, reponse=right))
    return candidates


def _dedupe_quiz_rows(rows: List[QuizRow]) -> List[QuizRow]:
    seen: set[tuple] = set()
    unique: List[QuizRow] = []
    for r in rows:
        pkey = tuple((L, _norm(t)) for L, t in r.propositions)
        key = (_norm(r.question), _norm(r.reponse), pkey)
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return unique


# Plusieurs strategies : certains PDF n'ont pas de lignes exploitables avec les defauts.
_TABLE_STRATEGIES: Tuple[Optional[dict], ...] = (
    None,
    {"vertical_strategy": "text", "horizontal_strategy": "text"},
)


def extract_quiz_rows_from_pdf(pdf_path: str) -> Tuple[List[QuizRow], List[str]]:
    """
    Extrait (question, reponse, propositions A/B/...) d'un PDF de correction.
    Retourne (rows, warnings). Les bonnes reponses viennent de la colonne `reponses`.
    """
    warnings: List[str] = []

    try:
        import pdfplumber  # type: ignore
    except ModuleNotFoundError:
        warnings.append(
            "La librairie 'pdfplumber' est absente de l'environnement Python du serveur "
            "(souvent le dossier .venv). Activez ce venv puis : python -m pip install pdfplumber"
        )
        return [], warnings
    except Exception as e:
        warnings.append(f"Impossible de charger 'pdfplumber' : {e}")
        return [], warnings

    unique: List[QuizRow] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for ts in _TABLE_STRATEGIES:
                rows: List[QuizRow] = []
                inter_table_carry: List[str] = []
                for page in pdf.pages:
                    page_had_rows = False
                    try:
                        if ts is None:
                            tables = page.extract_tables() or []
                        else:
                            tables = page.extract_tables(table_settings=ts) or []
                    except Exception:
                        tables = []
                    for t in tables:
                        part = _iter_rows_from_table(t, inter_table_carry, rows)
                        if inter_table_carry and rows:
                            _merge_carry_into_last_row(rows, inter_table_carry)
                        rows.extend(part)
                        page_had_rows = page_had_rows or bool(part)

                    if not page_had_rows:
                        try:
                            text = page.extract_text() or ""
                        except Exception:
                            text = ""
                        rows.extend(list(_iter_rows_from_text(text)))

                unique = _dedupe_quiz_rows(rows)
                if unique:
                    break

            if not unique:
                full_parts: List[str] = []
                for page in pdf.pages:
                    try:
                        full_parts.append(page.extract_text() or "")
                    except Exception:
                        pass
                full_text = "\n".join(full_parts)
                if full_text.strip():
                    ift = _extract_from_ift_correction_text(full_text)
                    unique = _dedupe_quiz_rows(ift)
                    if unique:
                        warnings.append(
                            "Extraction realisee a partir du texte du PDF (tableaux non detectes)."
                        )
                    if not unique:
                        unique = _dedupe_quiz_rows(
                            list(_iter_rows_from_text(full_text))
                        )
    except Exception as e:
        warnings.append(f"Impossible de lire le PDF: {e}")
        return [], warnings

    if not unique:
        warnings.append(
            "Aucune question/reponse detectee dans le PDF (verifier les colonnes "
            "'questions', 'reponses' et eventuellement A, B, C, D)."
        )

    return unique, warnings
