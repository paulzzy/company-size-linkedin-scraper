import os
from linkedin_api import Linkedin
import linkedin_api
from dotenv import load_dotenv
from rich.console import Console
from rich.traceback import install
from rich.prompt import Prompt
import webbrowser
from pathlib import Path
import csv
from typing import Literal
from typing import TypedDict
from collections import OrderedDict

load_dotenv()
install()
console = Console()
MODULE_PATH = os.path.dirname(os.path.realpath(__file__))

INPUT_PATH = os.path.join(MODULE_PATH, "company_names.txt")
OUTPUT_PATH = os.path.join(MODULE_PATH, "company_sizes.csv")

USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
line_num_last_written = 0


class CompanyData(TypedDict):
    linkedin_page_name: str | Literal["linkedin page not found"] | None
    size_code: Literal[1, 2, 3, 4, "size not found"] | None
    size_range_start: int | Literal["size not found"] | None


def classify_size(
    size_range_start: int | Literal["size not found"] | None,
) -> Literal[1, 2, 3, 4, "size not found"]:
    """
    For staff size ranges used by LinkedIn see https://learn.microsoft.com/en-us/linkedin/shared/references/reference-tables/company-size-codes
    """
    match size_range_start:
        case "size not found":
            return "size not found"
        case None:
            return "size not found"
        case size if size in range(0, 51):
            return 1
        case size if size in range(51, 1001):
            return 2
        case size if size in range(1001, 10_001):
            return 3
        case size if size > 10_000:
            return 4

    raise ValueError(
        f"Unrecognized starting number for staff size range: " f"{size_range_start}"
    )


with open(INPUT_PATH, "r") as names_file:
    companies: dict[str, CompanyData] = OrderedDict(
        {
            name: {
                "linkedin_page_name": None,
                "size_code": None,
                "size_range_start": None,
            }
            for name in names_file.read().splitlines()
        }
    )

try:
    Path(OUTPUT_PATH).touch(exist_ok=False)
except FileExistsError:
    # Recover progress from existing CSV file with company data
    with open(OUTPUT_PATH, "r") as sizes_file:
        reader = csv.reader(sizes_file)
        for size_code, size_range_start, linkedin_page_name, name in reader:
            companies[name]["linkedin_page_name"] = linkedin_page_name
            companies[name]["size_code"] = (
                int(size_code)  # type: ignore
                if size_code in ["1", "2", "3", "4"]
                else "size not found"
            )
            companies[name]["size_range_start"] = (
                int(size_range_start)
                if size_range_start.isdecimal()
                else "size not found"
            )

    with open(OUTPUT_PATH, "r") as sizes_file:
        line_num_last_written = sum(1 for _ in sizes_file)

api = Linkedin(USERNAME, PASSWORD)
# HACK: Disable evasion, which slows down the program by sleeping
# Since calling the API must wait for user input, should avoid rate limits already
# See https://github.com/tomquirk/linkedin-api/blob/e66bb5e217ab3383f4c2a6a25f8cd793b5b20b61/linkedin_api/linkedin.py#L37
linkedin_api.linkedin.default_evade = lambda *args, **kwargs: None

for line_num, name in enumerate(companies, 1):
    if companies[name]["size_code"]:
        console.print(
            f"[{line_num}/{len(companies)}] {name}: Already know it has at least "
            f"{companies[name]['size_range_start']} staff "
            f"(size code {companies[name]['size_code']})"
        )
    else:
        # `search_company` method is currently broken
        # See https://github.com/tomquirk/linkedin-api/issues/313
        # HACK: prompt user to manually input the company LinkedIn page URL
        search_page = f"https://www.linkedin.com/search/results/companies/?keywords={name}&spellCorrectionEnabled=false"
        console.print(
            f"[{line_num}/{len(companies)}] {name}: "
            f'Opening search page "{search_page}"...'
        )
        webbrowser.open(search_page)
        while True:
            linkedin_url = Prompt.ask(
                f"[{line_num}/{len(companies)}] {name}: "
                f'Input LinkedIn URL ("s" to skip): '
            )

            if linkedin_url == "s":
                companies[name]["linkedin_page_name"] = "linkedin page not found"
                companies[name]["size_range_start"] = "size not found"
                break

            try:
                # E.g. "google" from "https://www.linkedin.com/company/google/"
                # or "ucla" from "https://www.linkedin.com/school/ucla/"
                companies[name]["linkedin_page_name"] = linkedin_url.split("/")[4]

                console.print(
                    f"[{line_num}/{len(companies)}] {name}: Searching for "
                    f"{companies[name]['linkedin_page_name']}..."
                )

                details = api.get_company(companies[name]["linkedin_page_name"])
                companies[name]["size_range_start"] = details["staffCountRange"][
                    "start"
                ]
            except KeyError:
                console.print_exception()
                console.print(
                    f"[{line_num}/{len(companies)}] {name}: "
                    f"LinkedIn page may be missing staff size data"
                )
            except Exception:
                console.print_exception()
                continue
            break

        companies[name]["size_code"] = classify_size(
            companies[name]["size_range_start"]  # type: ignore
        )
        console.print(
            f"[{line_num}/{len(companies)}] {name}: Full data: {companies[name]}"
        )

    with open(OUTPUT_PATH, "r") as sizes_file:
        ends_with_newline = sizes_file.read().endswith("\n")

    with open(OUTPUT_PATH, "a") as sizes_file:
        if not ends_with_newline and os.path.getsize(OUTPUT_PATH) > 0:
            sizes_file.write("\n")
        if line_num > line_num_last_written:
            writer = csv.writer(sizes_file)
            writer.writerow(
                [
                    companies[name]["size_code"],
                    companies[name]["size_range_start"],
                    companies[name]["linkedin_page_name"],
                    name,
                ]
            )
