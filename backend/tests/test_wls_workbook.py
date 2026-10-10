import io
import zipfile

import pytest

from app.market.wls_workbook import prepare_workbook


def workbook(cells):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            """<workbook
          xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Feuil1" r:id="rId1"/></sheets></workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<Relationships>
          <Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f"""<worksheet
          xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <sheetData>{cells}</sheetData></worksheet>""",
        )
    return stream.getvalue()


def test_workbook_preserves_identifier_and_never_uses_file_dates_for_composition():
    raw = workbook('<row><c r="A1" t="inlineStr"><is><t>005930 KS Equity</t></is></c></row>')
    data = prepare_workbook(raw, "supplied.xlsx", "Liste WLS fournie par l'utilisateur")
    assert data.records[0].bloomberg_ticker == "005930"
    assert data.composition_as_of is None
    assert data.source_url is None and data.partial


@pytest.mark.parametrize(
    "cells",
    [
        '<row><c r="A1"><v>5930</v></c></row>',
        '<row><c r="A1" t="str"><f>REMOTE()</f><v>005930 KS Equity</v></c></row>',
        '<row><c r="B1" t="inlineStr"><is><t>AAPL US Equity</t></is></c></row>',
        '<row><c r="A1" t="inlineStr"><is><t>AAPL US Equity</t></is></c></row>'
        '<row><c r="A2" t="inlineStr"><is><t>AAPL US Equity</t></is></c></row>',
    ],
)
def test_workbook_rejects_numeric_identifiers_formulas_unexpected_columns_and_duplicates(cells):
    with pytest.raises(ValueError):
        prepare_workbook(workbook(cells), "supplied.xlsx", "Liste WLS fournie par l'utilisateur")
