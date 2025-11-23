# parser.py
import re
import uuid
from typing import List, Dict

# Patterns
# question start like "1." at line start
QUESTION_START_RE = re.compile(r'(?m)^\s*(\d+)\.\s*')

# line-start option like "(1) text" or "1) text"
LINE_OPTION_RE = re.compile(r'(?m)^\s*\(?\s*([1-9])\s*\)?\s*[\.\)]?\s*(.+)$')

# inline options like "(1) opt1 (2) opt2 (3) opt3 (4) opt4"
INLINE_NUMERIC_OPTIONS_RE = re.compile(r'\(\s*([1-9])\s*\)\s*([^\(]+)')

# alternative: A. / (A) style
LINE_ALPHA_OPTION_RE = re.compile(r'(?m)^\s*\(?\s*([A-Da-d])\s*\)?\s*[\.\)]?\s*(.+)$')
INLINE_ALPHA_OPTIONS_RE = re.compile(r'\(\s*([A-Da-d])\s*\)\s*([^(\n]+)')

# answer patterns (Ans., Answer, Ans)
ANS_RE = re.compile(r'(?i)ans(?:wer)?\s*[:\.\-]?\s*\(?\s*([A-Da-d0-9, ]+)\s*\)?')

def parse_questions_from_text(full_text: str) -> List[Dict]:
    """
    Parse questions from the full PDF text.
    Returns list of dicts:
      { id, number, text, options: [.. up to 4], correctIndex: int or list or None, raw_block, page_num_hint (optional) }
    Notes:
     - handles numeric (1)-(4) option markers and A/B style
     - if no options found, creates 4 blank slots for editing
     - if answer found like 'Ans. (2)' sets correctIndex to 0-based int; if multiple answers, stores list of indices
    """
    if not full_text:
        return []

    # Normalize line endings
    t = re.sub(r'\r\n?', '\n', full_text)
    # We will find question start indices
    starts = [m for m in QUESTION_START_RE.finditer(t)]
    q_blocks = []
    if not starts:
        # fallback: split by double newlines into paragraphs
        parts = [p.strip() for p in re.split(r'\n\s*\n', t) if p.strip()]
        for p in parts:
            q_blocks.append((None, p))
    else:
        for i, m in enumerate(starts):
            qnum = m.group(1)
            start_idx = m.start()
            end_idx = starts[i+1].start() if i+1 < len(starts) else len(t)
            block = t[start_idx:end_idx].strip()
            q_blocks.append((qnum, block))

    questions = []
    for qnum, block in q_blocks:
        raw = block

        # Try to find inline numeric options first (common JEE style)
        inline_num = INLINE_NUMERIC_OPTIONS_RE.findall(block)
        options = []
        if inline_num and len(inline_num) >= 2:
            # inline_num returns list of tuples (num, text)
            # We need to order by the numeric label (1..)
            # But the regex finds them in order; still safe to sort by int(label)
            items = sorted(((int(lbl), txt.strip()) for lbl, txt in inline_num), key=lambda x: x[0])
            options = [txt for _, txt in items]
        else:
            # Try line-based numeric options
            line_opts = LINE_OPTION_RE.findall(block)
            if line_opts and len(line_opts) >= 2:
                items = sorted(((int(lbl), txt.strip()) for lbl, txt in line_opts), key=lambda x: x[0])
                options = [txt for _, txt in items]

        # If still no numeric options, try alpha style inline or line-based
        if not options:
            inline_alpha = INLINE_ALPHA_OPTIONS_RE.findall(block)
            if inline_alpha and len(inline_alpha) >= 2:
                items = sorted(((lbl.upper(), txt.strip()) for lbl, txt in inline_alpha), key=lambda x: x[0])
                options = [txt for _, txt in items]
            else:
                line_alpha = LINE_ALPHA_OPTION_RE.findall(block)
                if line_alpha and len(line_alpha) >= 2:
                    # sort by A,B,C...
                    items = sorted(((lbl.upper(), txt.strip()) for lbl, txt in line_alpha), key=lambda x: x[0])
                    options = [txt for _, txt in items]

        # If options found, trim/normalize to at most 4
        if options:
            # Some options might include trailing 'Ans.' accidentally — strip 'Ans' fragments
            cleaned = []
            for opt in options:
                # remove trailing 'Ans' phrases that might get included
                cleaned_opt = re.sub(r'(?i)\bAns\b.*$', '', opt).strip()
                cleaned.append(cleaned_opt)
            options = cleaned[:4]
        else:
            # No options found: create 4 blank slots (user can fill them)
            options = ["", "", "", ""]

        # Find answer (Ans.) in block
        correctIndex = None
        ans_match = ANS_RE.search(block)
        if ans_match:
            ans_text = ans_match.group(1).strip()
            # Ans can be "2" or "2,4" or "A" or "A,C"
            # Normalize: split by comma or space
            parts = re.split(r'[,\s]+', ans_text)
            indices = []
            for p in parts:
                if not p:
                    continue
                if p.isdigit():
                    val = int(p) - 1
                    if 0 <= val < len(options):
                        indices.append(val)
                else:
                    # letter
                    ch = p[0].upper()
                    if ch >= 'A' and ch <= 'D':
                        idx = ord(ch) - ord('A')
                        if 0 <= idx < len(options):
                            indices.append(idx)
            if indices:
                # if multiple answers, store list; if single, store single int
                correctIndex = indices[0] if len(indices) == 1 else indices

        # Also try to find an answer noted elsewhere: sometimes at file end. We'll not parse end-of-file answers here.
        # Build question dict
        qdict = {
            "id": str(uuid.uuid4()),
            "number": int(qnum) if qnum and qnum.isdigit() else None,
            "text": block,
            "options": options,
            "correctIndex": correctIndex,
            "raw": raw
        }
        questions.append(qdict)

    return questions
