# -*- coding: utf-8 -*-
"""TCP Socket Tool 사용 설명서(docx)를 만듭니다."""

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

NAVY = "1B3A4B"
TEAL = "2F6F8F"
LINE = "D5DEE3"
PALE = "F4F7F8"
TIP = "E7F3F7"
NOTE = "FFF6E8"
WHITE = "FFFFFF"
INK = RGBColor(0x1F, 0x2A, 0x30)
MUTED = RGBColor(0x5C, 0x6B, 0x73)
FONT = "맑은 고딕"


def shade(cell, color):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), color)
    tc_pr.append(shd)


def set_cell_border(cell, color="D5DEE3", sz="4"):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), sz)
        element.set(qn("w:color"), color)
        borders.append(element)
    tc_pr.append(borders)


def set_cell_margins(cell, top=60, bottom=60, left=100, right=100):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for name, value in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        node = OxmlElement(f"w:{name}")
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")
        mar.append(node)
    tc_pr.append(mar)


def font_run(run, size=11, bold=False, color=INK, name=FONT):
    run.font.name = name
    run.font.size = Pt(size)
    run.bold = bold
    run.font.color.rgb = color
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.find(qn("w:rFonts"))
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.append(r_fonts)
    for key in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        r_fonts.set(qn(key), name)


def add_text(paragraph, text, size=11, bold=False, color=INK):
    run = paragraph.add_run(text)
    font_run(run, size, bold, color)
    return run


def style_paragraph(paragraph, before=0, after=6, line=1.08):
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    fmt.line_spacing = line
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE


def set_style(style, size, bold=False, color=INK, before=0, after=6):
    style.font.name = FONT
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = color
    r_pr = style.element.get_or_add_rPr()
    r_fonts = r_pr.find(qn("w:rFonts"))
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.append(r_fonts)
    for key in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        r_fonts.set(qn(key), FONT)
    style.paragraph_format.space_before = Pt(before)
    style.paragraph_format.space_after = Pt(after)


def prevent_row_split(row):
    tr = row._tr
    tr_pr = tr.get_or_add_trPr()
    cant = OxmlElement("w:cantSplit")
    tr_pr.append(cant)


def make_table(doc, headers, rows, widths):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        cell.text = ""
        paragraph = cell.paragraphs[0]
        style_paragraph(paragraph, 0, 0, 1.0)
        add_text(paragraph, header, 10, True, RGBColor(255, 255, 255))
        shade(cell, NAVY)
        set_cell_border(cell, NAVY, "4")
        set_cell_margins(cell)
        cell.width = Cm(widths[index])
    prevent_row_split(table.rows[0])
    for r_index, row in enumerate(rows):
        for c_index, value in enumerate(row):
            cell = table.rows[r_index + 1].cells[c_index]
            cell.text = ""
            paragraph = cell.paragraphs[0]
            style_paragraph(paragraph, 0, 0, 1.05)
            add_text(paragraph, value, 10, c_index == 0)
            shade(cell, WHITE if r_index % 2 == 0 else PALE)
            set_cell_border(cell, LINE, "4")
            set_cell_margins(cell)
            cell.width = Cm(widths[c_index])
        prevent_row_split(table.rows[r_index + 1])
    return table


def callout(doc, title, body, fill=TIP):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    cell.text = ""
    title_p = cell.paragraphs[0]
    style_paragraph(title_p, 0, 2, 1.0)
    add_text(title_p, title, 10, True, RGBColor(0x1B, 0x3A, 0x4B))
    body_p = cell.add_paragraph()
    style_paragraph(body_p, 0, 0, 1.08)
    add_text(body_p, body, 10)
    shade(cell, fill)
    set_cell_border(cell, TEAL if fill == TIP else "E2C48A", "8")
    set_cell_margins(cell, 80, 80, 140, 140)
    spacer = doc.add_paragraph()
    style_paragraph(spacer, 0, 2, 1.0)
    return table


def heading(doc, text):
    paragraph = doc.add_paragraph()
    style_paragraph(paragraph, 14, 6, 1.0)
    add_text(paragraph, text, 16, True, RGBColor(0x1B, 0x3A, 0x4B))
    # 제목 아래 짧은 선
    rule = doc.add_paragraph()
    style_paragraph(rule, 0, 8, 1.0)
    p_pr = rule._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "12")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), TEAL)
    p_bdr.append(bottom)
    p_pr.append(p_bdr)
    return paragraph


def subhead(doc, text):
    paragraph = doc.add_paragraph()
    style_paragraph(paragraph, 8, 4, 1.0)
    add_text(paragraph, text, 12, True, RGBColor(0x2F, 0x6F, 0x8F))
    return paragraph


def body(doc, text):
    paragraph = doc.add_paragraph()
    style_paragraph(paragraph, 0, 6, 1.15)
    add_text(paragraph, text, 11)
    return paragraph


def bullet(doc, text):
    paragraph = doc.add_paragraph()
    style_paragraph(paragraph, 0, 3, 1.08)
    paragraph.paragraph_format.left_indent = Cm(0.6)
    add_text(paragraph, "·  " + text, 11)
    return paragraph


def steps(doc, items):
    for index, text in enumerate(items, 1):
        paragraph = doc.add_paragraph()
        style_paragraph(paragraph, 1, 3, 1.08)
        paragraph.paragraph_format.left_indent = Cm(0.75)
        paragraph.paragraph_format.first_line_indent = Cm(-0.75)
        add_text(paragraph, f"{index}  ", 11, True, RGBColor(0x2F, 0x6F, 0x8F))
        add_text(paragraph, text, 11)


def add_page_field(paragraph):
    run = paragraph.add_run()
    font_run(run, 9, False, MUTED)

    def fld(kind):
        node = OxmlElement("w:fldChar")
        node.set(qn("w:fldCharType"), kind)
        run._r.append(node)

    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(separate)
    text = OxmlElement("w:t")
    text.text = "1"
    run._r.append(text)
    run._r.append(end)


def build():
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)
    section.top_margin = Cm(1.6)
    section.bottom_margin = Cm(1.6)
    section.header_distance = Cm(0.6)
    section.footer_distance = Cm(0.6)

    set_style(doc.styles["Normal"], 11, False, INK, 0, 6)

    header = section.header
    header.is_linked_to_previous = False
    hp = header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    style_paragraph(hp, 0, 0, 1.0)
    add_text(hp, "TCP Socket Tool", 9, True, RGBColor(0x1B, 0x3A, 0x4B))
    add_text(hp, "   사용 설명서", 9, False, MUTED)

    footer = section.footer
    footer.is_linked_to_previous = False
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.LEFT
    style_paragraph(fp, 0, 0, 1.0)
    add_text(fp, "C:\\TcpSocketTool\\TcpSocketTool.exe", 9, False, MUTED)
    add_text(fp, "          ", 9)
    add_page_field(fp)

    banner = doc.add_table(rows=1, cols=1)
    banner.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = banner.cell(0, 0)
    cell.text = ""
    kicker = cell.paragraphs[0]
    style_paragraph(kicker, 0, 2, 1.0)
    add_text(kicker, "SOCKET TEST GUIDE", 9, True, RGBColor(0xB7, 0xD4, 0xE2))
    title = cell.add_paragraph()
    style_paragraph(title, 0, 2, 1.0)
    add_text(title, "TCP 소켓 도구", 26, True, RGBColor(255, 255, 255))
    sub = cell.add_paragraph()
    style_paragraph(sub, 2, 0, 1.08)
    add_text(sub, "서버와 클라이언트로 TCP 전문을 보내고 받는 방법", 12, False, RGBColor(0xD5, 0xE6, 0xEE))
    shade(cell, NAVY)
    set_cell_border(cell, NAVY, "4")
    set_cell_margins(cell, 160, 160, 200, 200)

    gap = doc.add_paragraph()
    style_paragraph(gap, 8, 2, 1.0)
    add_text(gap, "실행 파일    C:\\TcpSocketTool\\TcpSocketTool.exe", 11, False, MUTED)

    body(doc, "운영 중인 TCP 소켓과 전문을 주고받을 때 쓰는 프로그램입니다. 포트를 열어 서버가 될 수도 있고, 상대 주소로 접속하는 클라이언트가 될 수도 있습니다.")

    heading(doc, "1. 실행")
    steps(doc, [
        "TcpSocketTool.exe 를 더블클릭합니다. 처음에는 몇 초 걸릴 수 있습니다.",
        "포트를 열 때 Windows 방화벽 창이 뜨면 허용합니다.",
        "프로그램을 닫았다가 다시 켜면 마지막 IP, 포트, 구분자, 문자셋이 그대로 열립니다.",
    ])
    callout(doc, "설정이 기억되는 곳", "접속 설정은 C:\\TcpSocketTool\\config.json 에 저장됩니다. 전문 양식과는 별도 파일입니다.")

    heading(doc, "2. 화면")
    body(doc, "위쪽은 연결과 구분자, 왼쪽은 보관한 전문, 가운데는 입력, 오른쪽은 대상과 보내기입니다.")
    make_table(
        doc,
        ["이름", "하는 일"],
        [
            ["SERVER / CLIENT", "서버로 기다릴지, 클라이언트로 붙을지 고릅니다."],
            ["IP / PORT", "주소와 포트입니다. 서버 기본값은 0.0.0.0 / 35000 입니다."],
            ["BIND / CONNECT", "서버는 BIND, 클라이언트는 CONNECT 입니다. 연결 중에는 CLOSE 로 바뀝니다."],
            ["CLEAN", "위쪽 로그만 지웁니다. 연결은 끊지 않습니다."],
            ["DELIMITER", "전문 앞뒤에 붙는 구분자입니다. 기본값은 NULL (0x00) 입니다."],
            ["송신 시 자동추가", "켜 두면 본문만 적어도 구분자가 한 번 붙습니다."],
            ["문자셋", "UTF-8 또는 ASCII 입니다. 기본값은 UTF-8 입니다."],
            ["대상", "오른쪽에 붙은 클라이언트가 IP:포트로 보입니다. 여러 곳을 고를 수 있습니다."],
            ["전체선택", "붙어 있는 클라이언트를 모두 선택합니다."],
            ["STRING / BYTE", "보낼 내용을 글자로 넣을지, 바이트로 넣을지 고릅니다."],
            ["String Add", "입력한 글을 STRING 칸에 그대로 붙입니다."],
            ["Byte Add", "입력한 바이트 하나를 BYTE 칸에 붙입니다."],
            ["SEND", "선택된 탭의 내용을, 대상에서 고른 곳으로 보냅니다. Ctrl+Enter 도 같습니다."],
        ],
        [4.6, 12.6],
    )

    heading(doc, "3. 서버로 열기")
    steps(doc, [
        "SERVER 를 고릅니다. IP는 보통 0.0.0.0 입니다.",
        "포트를 입력합니다. 예: 35000",
        "BIND 를 누릅니다.",
        "로그에 channelActive listen 0.0.0.0:35000 이 나오면 대기 중입니다.",
        "상대가 붙으면 channelActive 와 그 주소가 나옵니다.",
        "끊을 때는 CLOSE 를 누릅니다.",
    ])
    callout(doc, "0.0.0.0", "이 PC로 들어오는 접속을 모두 받는다는 뜻입니다. 이 PC 안에서만 시험할 때는 클라이언트의 IP를 127.0.0.1 로 둡니다.")

    heading(doc, "4. 클라이언트로 붙기")
    steps(doc, [
        "CLIENT 를 고릅니다.",
        "상대 IP와 포트를 입력합니다.",
        "CONNECT 를 누릅니다.",
        "로그에 channelActive 가 나오면 연결된 것입니다.",
        "끊을 때는 CLOSE 를 누릅니다.",
    ])
    body(doc, "서버가 먼저 BIND 되어 있어야 클라이언트가 접속할 수 있습니다.")

    heading(doc, "5. 구분자")
    body(doc, "구분자는 한 번만 고릅니다. 송신 시 자동추가가 켜져 있으면 본문에 구분자를 다시 적지 않아도 됩니다. 이미 붙어 있으면 한 번 더 붙이지 않습니다.")
    make_table(
        doc,
        ["구분자", "붙는 위치"],
        [
            ["NULL (0x00)", "본문 뒤에 0x00. 프로그램을 처음 열면 이 값입니다."],
            ["LINE (CR LF)", "본문 뒤에 0x0D 다음 0x0A. 10진수로는 13 10 입니다."],
            ["STX/ETX", "앞에 STX(0x02), 뒤에 ETX(0x03). 둘은 한 쌍입니다."],
            ["CR (0x0D)", "본문 뒤에 0x0D(10진수 13)만 붙습니다."],
            ["LF (0x0A)", "본문 뒤에 0x0A(10진수 10)만 붙습니다."],
            ["없음", "구분자를 붙이지 않습니다."],
            ["직접입력", "바이트로 적습니다. 0D 0A, 13 10, \\r\\n 은 LINE과 같습니다."],
        ],
        [4.2, 13.0],
    )
    doc.add_paragraph()
    callout(
        doc,
        "예시",
        "구분자 NULL, 자동추가가 켜진 상태에서 STRING에 - 를 보내면 실제 바이트는 45 0 입니다. 45는 '-' 이고 0은 NULL 입니다.\n"
        "STX/ETX 에서 같은 본문을 보내면 2 45 3 입니다.",
        NOTE,
    )
    body(doc, "받은 데이터는 구분자가 늦게 와도 기다리지 않습니다. 도착하는 즉시 로그에 나옵니다.")
    callout(doc, "직접입력", "아스키 단어를 적는 칸이 아닙니다. 0D 0A 나 13 10 처럼 바이트를 적습니다. CRLF 라고 글자로 적으면 C, R, L, F 네 글자가 들어갑니다.")

    heading(doc, "6. 보낼 대상")
    body(doc, "오른쪽 대상 칸에 붙은 클라이언트가 IP:포트로 보입니다. 새로 붙으면 목록에 추가되고, 처음에는 선택된 상태입니다. 끊기면 목록에서 빠집니다.")
    steps(doc, [
        "한 곳만 보내려면 그 주소만 클릭합니다.",
        "여러 곳이면 Ctrl 을 누른 채 주소를 클릭합니다. Shift 로 범위를 고를 수도 있습니다.",
        "전체선택을 누르면 붙어 있는 모두에게 보냅니다.",
        "아무것도 고르지 않고 SEND 하면 \"보낼 대상을 선택하세요\" 가 나옵니다.",
    ])

    heading(doc, "7. 보내기")
    subhead(doc, "STRING으로 보내기")
    steps(doc, [
        "STRING 탭을 엽니다.",
        "전문 본문만 입력합니다. 구분자는 넣지 않아도 됩니다.",
        "SEND 를 누릅니다. 로그에 send Byte 와 send String 이 남습니다.",
    ])
    subhead(doc, "BYTE로 보내기")
    steps(doc, [
        "BYTE 탭을 엽니다.",
        "바이트를 공백으로 나눠 입력합니다. 10진수는 45 0, 16진수는 2D 00 또는 0x2D 0x00 입니다.",
        "아래 HEX 미리보기로 값을 확인합니다.",
        "SEND 를 누릅니다. 자동추가가 켜져 있으면 적은 값 뒤에도 구분자가 붙습니다.",
    ])
    callout(doc, "구분자를 직접 넣을 때", "BYTE 칸에 구분자 바이트까지 같이 적으면 됩니다. 이미 끝에 있으면 자동추가가 켜져 있어도 한 번 더 붙지 않습니다.")
    make_table(
        doc,
        ["버튼", "결과"],
        [
            ["String Add", "오른쪽 칸의 글이 STRING에 그대로 붙습니다. 123 은 123 이고, 49 50 51 로 바뀌지 않습니다."],
            ["Byte Add", "바이트 하나(0, 45, 0x0A)가 BYTE 칸 끝에 붙고 BYTE 탭으로 이동합니다."],
        ],
        [3.6, 13.6],
    )
    doc.add_paragraph()
    body(doc, "SEND 는 지금 열린 탭의 내용을, 대상에서 선택된 주소로만 보냅니다. 여러 곳을 골랐으면 로그에 보낸 곳 수가 같이 나옵니다.")

    heading(doc, "8. 받기")
    body(doc, "받은 내용은 위쪽 로그만 봅니다. 왼쪽 전문 목록에는 생기지 않고, 파일에도 저장되지 않습니다.")
    make_table(
        doc,
        ["로그", "의미"],
        [
            ["Byte:45 13 10", "도착한 바이트를 10진수로 보여 줍니다."],
            ["String:-", "그 바이트를 문자셋으로 읽은 글입니다. 구분자와 줄바꿈은 글에서 빠져 있습니다."],
        ],
        [4.4, 12.8],
    )
    doc.add_paragraph()
    body(doc, "서버일 때는 어느 주소에서 왔는지도 같이 나옵니다. CLEAN 은 이 로그만 지웁니다.")
    body(doc, "위쪽의 수신 시 응답을 켜면, 데이터가 들어온 그 소켓으로 바로 답을 씁니다. 옆 칸이 비어 있으면 방금 받은 바이트를 그대로 돌려주고, 칸에 글을 적으면 그 글을 현재 문자셋과 구분자 설정으로 보내 줍니다. 로그에 send 와 그 주소가 보이면 실제로 송신된 것입니다. 상대가 NULL 구분자면 이 프로그램도 NULL 이어야 상대 화면에 나타납니다.")

    heading(doc, "9. 자주 쓰는 전문")
    steps(doc, [
        "STRING에 양식을 만든 뒤 보관을 누릅니다.",
        "왼쪽 목록에 ★ 와 함께 추가되고, 바로 파일에 저장됩니다.",
        "프로그램을 껐다 켜도 ★ 목록은 다시 나타납니다.",
        "항목을 고르고 불러오기를 누르거나 더블클릭하면 STRING 칸에 들어갑니다.",
        "삭제를 누르면 목록과 파일에서 함께 지워집니다.",
    ])
    callout(doc, "저장 위치", "C:\\TcpSocketTool\\messages.json\n보관은 STRING 칸의 내용만 저장합니다. 수신된 전문은 이 목록에 들어가지 않습니다.")

    heading(doc, "10. 로그에 나오는 말")
    make_table(
        doc,
        ["표시", "의미"],
        [
            ["channelRegistered", "소켓이 준비되었습니다."],
            ["channelActive", "서버가 대기 중이거나, 상대와 연결되었습니다."],
            ["channelRead", "데이터를 받았습니다."],
            ["channelReadComplete", "이번 수신 처리를 마쳤습니다."],
            ["channelInactive", "연결이 끊어졌습니다."],
            ["channelUnregistered", "소켓이 해제되었습니다."],
            ["send", "보낸 내용입니다."],
            ["exceptionCaught", "오류입니다. 뒤에 나오는 문장이 원인입니다."],
        ],
        [5.2, 12.0],
    )

    heading(doc, "11. 다른 PC에 전달")
    body(doc, "TcpSocketTool.exe 파일 하나만 주면 실행됩니다. Python을 따로 설치하지 않아도 됩니다. 처음 실행은 몇 초 걸릴 수 있고, 서명되지 않은 파일이라 Windows 경고가 한 번 뜰 수 있습니다.")
    callout(doc, "같이 줄 파일", "지금 PC에 저장해 둔 양식까지 넘기려면 messages.json 을 실행 파일과 같은 폴더에 같이 둡니다. 설명서는 사용설명서.docx 입니다. 둘 다 없어도 프로그램은 실행됩니다.")

    heading(doc, "12. 자주 보는 상황")
    make_table(
        doc,
        ["상황", "확인할 곳"],
        [
            ["연결이 안 됩니다", "IP와 포트, 서버의 BIND 여부, 방화벽을 확인합니다."],
            ["상대가 못 받습니다", "구분자가 상대와 같은지 보고, 로그의 send Byte 숫자로 실제 값을 확인합니다."],
            ["글자가 깨집니다", "문자셋은 UTF-8 또는 ASCII 입니다. 기본값은 UTF-8 입니다."],
            ["일부에게만 보내고 싶습니다", "오른쪽 대상에서 보낼 주소만 선택합니다. Ctrl+클릭으로 여러 곳을 고릅니다."],
        ],
        [4.4, 12.8],
    )

    out = r"C:\TcpSocketTool\사용설명서.docx"
    doc.save(out)
    print(out)


if __name__ == "__main__":
    build()
