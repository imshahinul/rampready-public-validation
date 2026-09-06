#!/usr/bin/env python3

import hashlib
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


APP = Path(
    __file__
).resolve().parent

CONFIG_PATH = (
    APP
    / "config.json"
)

SEMANTIC_PATH = (
    APP
    / "frozen"
    / "semantic-contract.json"
)

HISTORY_PATH = (
    APP
    / "history.jsonl"
)

STATE_DIR = (
    APP
    / "state"
)

RUNS_DIR = (
    APP
    / "runs"
)


USER_AGENT = (
    "RampReady-Public-Validation/1.0 "
    "(bounded official-source diagnostic)"
)


ICON_STATUS = {
    "green.png":
        "OPEN",

    "yellow.png":
        "PARTIALLY_OPEN",

    "red-s.png":
        "SEASONAL_CLOSURE",

    "red.png":
        "CLOSED",

    "grey.png":
        "UNKNOWN",
}


def norm(value):

    value = html.unescape(
        str(
            value
            or ""
        )
    ).upper()

    value = value.replace(
        "&",
        " AND ",
    )

    value = re.sub(
        r"[^A-Z0-9]+",
        " ",
        value,
    )

    return " ".join(
        value.split()
    )


def clean_central_name(value):

    value = str(
        value
        or ""
    )

    value = re.sub(
        r"\(\s*Make a Reservation\s*\)",
        "",
        value,
        flags=re.I,
    )

    value = re.sub(
        r"\(\s*AL\s*\)\s*$",
        "",
        value,
        flags=re.I,
    )

    return norm(
        value
    )


class TableParser(HTMLParser):

    def __init__(self):

        super().__init__(
            convert_charrefs=True
        )

        self.rows = []
        self.row = None
        self.cell = None


    def handle_starttag(
        self,
        tag,
        attrs,
    ):

        tag = tag.lower()

        if tag == "tr":

            self.row = []

        elif (
            tag in {
                "td",
                "th",
            }
            and
            self.row is not None
        ):

            self.cell = {
                "text": [],
                "images": [],
            }

        elif (
            tag == "img"
            and
            self.cell is not None
        ):

            self.cell[
                "images"
            ].append(
                dict(
                    attrs
                )
            )


    def handle_data(
        self,
        data,
    ):

        if self.cell is not None:

            self.cell[
                "text"
            ].append(
                data
            )


    def handle_endtag(
        self,
        tag,
    ):

        tag = tag.lower()

        if (
            tag in {
                "td",
                "th",
            }
            and
            self.cell is not None
            and
            self.row is not None
        ):

            self.cell[
                "text"
            ] = " ".join(
                " ".join(
                    self.cell[
                        "text"
                    ]
                ).split()
            )

            self.row.append(
                self.cell
            )

            self.cell = None

        elif (
            tag == "tr"
            and
            self.row is not None
        ):

            if self.row:

                self.rows.append(
                    self.row
                )

            self.row = None
            self.cell = None


def central_status(cell):

    statuses = []

    for image in cell.get(
        "images",
        []
    ):

        image_name = Path(
            image.get(
                "src",
                ""
            )
        ).name.lower()

        if image_name in ICON_STATUS:

            statuses.append(
                ICON_STATUS[
                    image_name
                ]
            )


    if len(
        statuses
    ) == 1:

        return statuses[0]


    text = str(
        cell.get(
            "text",
            ""
        )
    ).strip()


    if (
        not statuses
        and
        "---" in text
    ):

        return "NO_FACILITY"


    return "UNPARSED"


def arcgis_status(value):

    mapping = {
        "OPEN":
            "OPEN",

        "PARTIAL":
            "PARTIALLY_OPEN",

        "PARTIALLY OPEN":
            "PARTIALLY_OPEN",

        "SEASONAL":
            "SEASONAL_CLOSURE",

        "SEASONAL CLOSURE":
            "SEASONAL_CLOSURE",

        "CLOSED":
            "CLOSED",

        "UNKNOWN":
            "UNKNOWN",

        "STATUS UNKNOWN":
            "UNKNOWN",
    }

    return mapping.get(
        norm(
            value
        ),
        "UNPARSED",
    )


def sha256_bytes(data):

    return hashlib.sha256(
        data
    ).hexdigest()


def load_json(path):

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def existing_history_dates():

    dates = set()

    if not HISTORY_PATH.exists():

        return dates


    for line in HISTORY_PATH.read_text(
        encoding="utf-8"
    ).splitlines():

        line = line.strip()

        if not line:
            continue

        try:

            item = json.loads(
                line
            )

        except json.JSONDecodeError:

            raise RuntimeError(
                "history.jsonl contains invalid JSON."
            )

        scheduled_date = item.get(
            "scheduled_date"
        )

        if scheduled_date:

            dates.add(
                scheduled_date
            )


    return dates


def activation_guard(
    config,
):

    observation = config[
        "observation"
    ]

    activation = observation.get(
        "activation_date"
    )

    final = observation.get(
        "final_date"
    )


    if (
        config.get(
            "status"
        )
        != "ACTIVE"
    ):

        print(
            "COLLECTOR STATUS: REFUSED"
        )

        print(
            "REASON: CONFIG_NOT_ACTIVE"
        )

        raise SystemExit(
            20
        )


    if not activation:

        print(
            "COLLECTOR STATUS: REFUSED"
        )

        print(
            "REASON: ACTIVATION_DATE_NOT_SET"
        )

        raise SystemExit(
            21
        )


    if not final:

        print(
            "COLLECTOR STATUS: REFUSED"
        )

        print(
            "REASON: FINAL_DATE_NOT_SET"
        )

        raise SystemExit(
            22
        )


    return (
        date.fromisoformat(
            activation
        ),
        date.fromisoformat(
            final
        ),
    )


def fetch(
    url,
    *,
    params=None,
    timeout=60,
):

    if params:

        query = urllib.parse.urlencode(
            params
        )

        separator = (
            "&"
            if "?" in url
            else "?"
        )

        url = (
            url
            + separator
            + query
        )


    request = urllib.request.Request(
        url,
        headers={
            "User-Agent":
                USER_AGENT,

            "Accept":
                "*/*",
        },
        method="GET",
    )


    try:

        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:

            data = response.read()

            return {
                "ok":
                    response.status
                    == 200,

                "http_code":
                    response.status,

                "data":
                    data,

                "error":
                    "",
            }


    except urllib.error.HTTPError as exc:

        try:
            data = exc.read()

        except Exception:
            data = b""

        return {
            "ok":
                False,

            "http_code":
                exc.code,

            "data":
                data,

            "error":
                str(
                    exc
                ),
        }


    except Exception as exc:

        return {
            "ok":
                False,

            "http_code":
                None,

            "data":
                b"",

            "error":
                (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
        }


def main():

    config = load_json(
        CONFIG_PATH
    )

    semantic = load_json(
        SEMANTIC_PATH
    )


    activation, final = activation_guard(
        config
    )


    now = datetime.now(
        timezone.utc
    )

    today = now.date()

    scheduled_date = (
        today.isoformat()
    )


    if today < activation:

        print(
            "COLLECTOR STATUS: REFUSED"
        )

        print(
            "REASON: BEFORE_ACTIVATION_DATE"
        )

        raise SystemExit(
            23
        )


    if today > final:

        print(
            "COLLECTOR STATUS: REFUSED"
        )

        print(
            "REASON: AFTER_FINAL_DATE"
        )

        raise SystemExit(
            24
        )


    if scheduled_date in existing_history_dates():

        print(
            "COLLECTOR STATUS: SKIP"
        )

        print(
            "REASON: DATE_ALREADY_RECORDED"
        )

        return


    facilities = semantic[
        "facilities"
    ]


    if len(
        facilities
    ) != 19:

        raise RuntimeError(
            "Semantic contract facility denominator is not 19."
        )


    if semantic[
        "central_status_field"
    ] != "Boat Ramps":

        raise RuntimeError(
            "Central semantic field changed."
        )


    if semantic[
        "arcgis_status_field"
    ] != "Boat":

        raise RuntimeError(
            "ArcGIS semantic field changed."
        )


    if semantic[
        "area_status_substitution_allowed"
    ] is not False:

        raise RuntimeError(
            "AreaStatus substitution became authorized."
        )


    boat_col = semantic[
        "central_boat_ramps_column_index"
    ]


    if boat_col != 3:

        raise RuntimeError(
            "Central Boat Ramps column is not frozen at index 3."
        )


    run_dir = (
        RUNS_DIR
        / scheduled_date
    )


    if run_dir.exists():

        raise RuntimeError(
            "Run directory already exists without accepted history entry."
        )


    run_dir.mkdir(
        parents=True,
        exist_ok=False,
    )


    central_result = fetch(
        config[
            "central"
        ][
            "url"
        ]
    )


    arcgis_result = fetch(
        config[
            "arcgis"
        ][
            "url"
        ],
        params={
            "f":
                "json",

            "where":
                "PSA_Entrance_XY_FY20_State='GA'",

            "outFields":
                (
                    "OBJECTID,"
                    "featureName,"
                    "recProjectSiteName,"
                    "Boat,"
                    "PrevBoat,"
                    "AreaStatus,"
                    "Notes"
                ),

            "returnGeometry":
                "false",
        },
    )


    central_raw = (
        run_dir
        / "central_ga_status.html"
    )

    arcgis_raw = (
        run_dir
        / "arcgis_ga_status.json"
    )


    central_raw.write_bytes(
        central_result[
            "data"
        ]
    )

    arcgis_raw.write_bytes(
        arcgis_result[
            "data"
        ]
    )


    central_retrieval_ok = (
        central_result[
            "ok"
        ]
        and
        len(
            central_result[
                "data"
            ]
        )
        > 1000
    )


    arcgis_retrieval_ok = (
        arcgis_result[
            "ok"
        ]
        and
        len(
            arcgis_result[
                "data"
            ]
        )
        > 1000
    )


    central_rows = []
    central_parser_ok = False
    central_updated = ""


    if central_retrieval_ok:

        try:

            central_text = central_result[
                "data"
            ].decode(
                "utf-8",
                errors="replace",
            )

            parser = TableParser()

            parser.feed(
                central_text
            )

            central_rows = parser.rows

            central_parser_ok = bool(
                central_rows
            )


            match = re.search(
                r"Updated\s*:\s*"
                r"([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})",
                central_text,
                flags=re.I,
            )

            if match:

                central_updated = match.group(
                    1
                )


        except Exception:

            central_parser_ok = False


    arc_records = []
    arcgis_parser_ok = False


    if arcgis_retrieval_ok:

        try:

            payload = json.loads(
                arcgis_result[
                    "data"
                ].decode(
                    "utf-8"
                )
            )


            if "error" not in payload:

                arc_records = [
                    feature.get(
                        "attributes",
                        {}
                    )
                    for feature
                    in payload.get(
                        "features",
                        []
                    )
                ]

                arcgis_parser_ok = bool(
                    arc_records
                )


        except Exception:

            arcgis_parser_ok = False


    comparisons = []


    for facility in facilities:

        facility_id = facility[
            "id"
        ]

        aliases = {
            norm(
                alias
            )
            for alias
            in facility[
                "aliases"
            ]
        }

        project = facility[
            "project"
        ]


        central_matches = []


        if central_parser_ok:

            for row in central_rows:

                if len(
                    row
                ) <= boat_col:

                    continue


                if (
                    clean_central_name(
                        row[0].get(
                            "text",
                            ""
                        )
                    )
                    in aliases
                ):

                    central_matches.append(
                        row
                    )


        arc_matches = []


        if arcgis_parser_ok:

            arc_matches = [
                record
                for record
                in arc_records
                if (
                    norm(
                        record.get(
                            "recProjectSiteName"
                        )
                    )
                    == norm(
                        project
                    )

                    and

                    norm(
                        record.get(
                            "featureName"
                        )
                    )
                    in aliases
                )
            ]


        central_value = ""


        if len(
            central_matches
        ) == 1:

            central_value = central_status(
                central_matches[0][
                    boat_col
                ]
            )


        arc_boat = ""
        arc_prev_boat = ""
        arc_area = ""
        arc_notes = ""


        if len(
            arc_matches
        ) == 1:

            record = arc_matches[0]

            arc_boat = arcgis_status(
                record.get(
                    "Boat"
                )
            )

            arc_prev_boat = str(
                record.get(
                    "PrevBoat"
                )
                or ""
            )

            arc_area = str(
                record.get(
                    "AreaStatus"
                )
                or ""
            )

            arc_notes = str(
                record.get(
                    "Notes"
                )
                or ""
            )


        comparable = (
            central_retrieval_ok
            and
            central_parser_ok
            and
            arcgis_retrieval_ok
            and
            arcgis_parser_ok
            and
            len(
                central_matches
            ) == 1
            and
            len(
                arc_matches
            ) == 1
            and
            central_value
            not in {
                "",
                "UNPARSED",
            }
            and
            arc_boat
            not in {
                "",
                "UNPARSED",
            }
        )


        comparisons.append({
            "facility_id":
                facility_id,

            "canonical_name":
                facility[
                    "name"
                ],

            "central_match_count":
                len(
                    central_matches
                ),

            "arcgis_match_count":
                len(
                    arc_matches
                ),

            "central_boat_ramps":
                central_value,

            "arcgis_boat":
                arc_boat,

            "arcgis_prev_boat":
                arc_prev_boat,

            "arcgis_area_status":
                arc_area,

            "arcgis_notes":
                arc_notes,

            "paired_comparable":
                comparable,

            "concordant":
                (
                    comparable
                    and
                    central_value
                    == arc_boat
                ),
        })


    if len(
        comparisons
    ) != 19:

        raise RuntimeError(
            "Expected 19 facility comparisons."
        )


    comparable_count = sum(
        item[
            "paired_comparable"
        ]
        for item
        in comparisons
    )


    concordant_count = sum(
        item[
            "concordant"
        ]
        for item
        in comparisons
    )


    run_record = {
        "artifact":
            "RAMPREADY_PUBLIC_PAIRED_OBSERVATION_V1",

        "observed_at_utc":
            now.isoformat(),

        "scheduled_date":
            scheduled_date,

        "central": {
            "http_code":
                central_result[
                    "http_code"
                ],

            "retrieval_ok":
                central_retrieval_ok,

            "parser_ok":
                central_parser_ok,

            "source_updated_date":
                central_updated,

            "raw_file":
                (
                    "runs/"
                    + scheduled_date
                    + "/central_ga_status.html"
                ),

            "raw_sha256":
                sha256_bytes(
                    central_result[
                        "data"
                    ]
                ),

            "error":
                central_result[
                    "error"
                ],
        },

        "arcgis": {
            "http_code":
                arcgis_result[
                    "http_code"
                ],

            "retrieval_ok":
                arcgis_retrieval_ok,

            "parser_ok":
                arcgis_parser_ok,

            "raw_file":
                (
                    "runs/"
                    + scheduled_date
                    + "/arcgis_ga_status.json"
                ),

            "raw_sha256":
                sha256_bytes(
                    arcgis_result[
                        "data"
                    ]
                ),

            "error":
                arcgis_result[
                    "error"
                ],
        },

        "facility_count":
            19,

        "paired_comparable_count":
            comparable_count,

        "concordant_count":
            concordant_count,

        "comparisons":
            comparisons,
    }


    result_file = (
        run_dir
        / "result.json"
    )


    result_file.write_text(
        json.dumps(
            run_record,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


    with HISTORY_PATH.open(
        "a",
        encoding="utf-8",
    ) as history:

        history.write(
            json.dumps(
                {
                    "scheduled_date":
                        scheduled_date,

                    "observed_at_utc":
                        now.isoformat(),

                    "paired_comparable_count":
                        comparable_count,

                    "concordant_count":
                        concordant_count,

                    "result_file":
                        (
                            "runs/"
                            + scheduled_date
                            + "/result.json"
                        ),

                    "central_retrieval_ok":
                        central_retrieval_ok,

                    "arcgis_retrieval_ok":
                        arcgis_retrieval_ok,
                },
                separators=(
                    ",",
                    ":",
                ),
            )
            + "\n"
        )


    state_record = {
        "latest_scheduled_date":
            scheduled_date,

        "latest_result_file":
            (
                "runs/"
                + scheduled_date
                + "/result.json"
            ),

        "updated_at_utc":
            now.isoformat(),
    }


    (
        STATE_DIR
        / "latest.json"
    ).write_text(
        json.dumps(
            state_record,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


    print(
        "COLLECTOR STATUS: RECORDED"
    )

    print(
        "SCHEDULED DATE:",
        scheduled_date,
    )

    print(
        "PAIRED COMPARABLE:",
        comparable_count,
        "/19",
    )

    print(
        "CONCORDANT:",
        concordant_count,
        "/19",
    )


if __name__ == "__main__":

    main()
