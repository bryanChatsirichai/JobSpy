from __future__ import annotations

import logging
import re
from itertools import cycle

import numpy as np
import requests
import tls_client
import urllib3
from markdownify import markdownify as md
from requests.adapters import HTTPAdapter, Retry

from jobspy.model import CompensationInterval, JobType, Site

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def create_logger(name: str):
    logger = logging.getLogger(f"JobSpy:{name}")
    logger.propagate = False
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        console_handler = logging.StreamHandler()
        format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
        formatter = logging.Formatter(format)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    return logger


class RotatingProxySession:
    def __init__(self, proxies=None):
        if isinstance(proxies, str):
            self.proxy_cycle = cycle([self.format_proxy(proxies)])
        elif isinstance(proxies, list):
            self.proxy_cycle = (
                cycle([self.format_proxy(proxy) for proxy in proxies])
                if proxies
                else None
            )
        else:
            self.proxy_cycle = None

    @staticmethod
    def format_proxy(proxy):
        """Utility method to format a proxy string into a dictionary."""
        if proxy.startswith("http://") or proxy.startswith("https://"):
            return {"http": proxy, "https": proxy}
        if proxy.startswith("socks5://"):
            return {"http": proxy, "https": proxy}
        return {"http": f"http://{proxy}", "https": f"http://{proxy}"}


class RequestsRotating(RotatingProxySession, requests.Session):
    def __init__(self, proxies=None, has_retry=False, delay=1, clear_cookies=False):
        RotatingProxySession.__init__(self, proxies=proxies)
        requests.Session.__init__(self)
        self.clear_cookies = clear_cookies
        self.allow_redirects = True
        self.setup_session(has_retry, delay)

    def setup_session(self, has_retry, delay):
        if has_retry:
            retries = Retry(
                total=3,
                connect=3,
                status=3,
                status_forcelist=[500, 502, 503, 504, 429],
                backoff_factor=delay,
            )
            adapter = HTTPAdapter(max_retries=retries)
            self.mount("http://", adapter)
            self.mount("https://", adapter)

    def request(self, method, url, **kwargs):
        if self.clear_cookies:
            self.cookies.clear()

        if self.proxy_cycle:
            next_proxy = next(self.proxy_cycle)
            if next_proxy["http"] != "http://localhost":
                self.proxies = next_proxy
            else:
                self.proxies = {}
        return requests.Session.request(self, method, url, **kwargs)


class TLSRotating(RotatingProxySession, tls_client.Session):
    def __init__(self, proxies=None):
        RotatingProxySession.__init__(self, proxies=proxies)
        tls_client.Session.__init__(self, random_tls_extension_order=True)

    def execute_request(self, *args, **kwargs):
        if self.proxy_cycle:
            next_proxy = next(self.proxy_cycle)
            if next_proxy["http"] != "http://localhost":
                self.proxies = next_proxy
            else:
                self.proxies = {}
        response = tls_client.Session.execute_request(self, *args, **kwargs)
        response.ok = response.status_code in range(200, 400)
        return response


def create_session(
    *,
    proxies: dict | str | None = None,
    ca_cert: str | None = None,
    is_tls: bool = True,
    has_retry: bool = False,
    delay: int = 1,
    clear_cookies: bool = False,
) -> requests.Session:
    """
    Creates a requests session with optional tls, proxy, and retry settings.
    :return: A session object
    """
    if is_tls:
        session = TLSRotating(proxies=proxies)
    else:
        session = RequestsRotating(
            proxies=proxies,
            has_retry=has_retry,
            delay=delay,
            clear_cookies=clear_cookies,
        )

    if ca_cert:
        session.verify = ca_cert

    return session


def set_logger_level(verbose: int):
    """
    Adjusts the logger's level. This function allows the logging level to be changed at runtime.

    Parameters:
    - verbose: int {0, 1, 2} (default=2, all logs)
    """
    if verbose is None:
        return
    level_name = {2: "INFO", 1: "WARNING", 0: "ERROR"}.get(verbose, "INFO")
    level = getattr(logging, level_name.upper(), None)
    if level is not None:
        for logger_name in logging.root.manager.loggerDict:
            if logger_name.startswith("JobSpy:"):
                logging.getLogger(logger_name).setLevel(level)
    else:
        raise ValueError(f"Invalid log level: {level_name}")


def markdown_converter(description_html: str):
    if description_html is None:
        return None
    markdown = md(description_html)
    return markdown.strip()

def plain_converter(decription_html:str):
    from bs4 import BeautifulSoup
    if decription_html is None:
        return None
    soup = BeautifulSoup(decription_html, "html.parser")
    text = soup.get_text(separator=" ")
    text = re.sub(r'\s+',' ',text)
    return text.strip()


def extract_emails_from_text(text: str) -> list[str] | None:
    if not text:
        return None
    email_regex = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    return email_regex.findall(text)


def get_enum_from_job_type(job_type_str: str) -> JobType | None:
    """
    Given a string, returns the corresponding JobType enum member if a match is found.
    """
    res = None
    for job_type in JobType:
        if job_type_str in job_type.value:
            res = job_type
    return res


def currency_parser(cur_str):
    # Remove any non-numerical characters
    # except for ',' '.' or '-' (e.g. EUR)
    cur_str = re.sub("[^-0-9.,]", "", cur_str)
    # Remove any 000s separators (either , or .)
    cur_str = re.sub("[.,]", "", cur_str[:-3]) + cur_str[-3:]

    if "." in list(cur_str[-3:]):
        num = float(cur_str)
    elif "," in list(cur_str[-3:]):
        num = float(cur_str.replace(",", "."))
    else:
        num = float(cur_str)

    return np.round(num, 2)


def remove_attributes(tag):
    for attr in list(tag.attrs):
        del tag[attr]
    return tag


def _salary_currency_from_text(text: str) -> str:
    if re.search(r"S\$|SGD", text, re.IGNORECASE):
        return "SGD"
    return "USD"


def _salary_interval_from_context(context: str) -> str | None:
    ctx = context.lower()
    if re.search(r"per\s+hour|/hour|\bhourly\b", ctx):
        return CompensationInterval.HOURLY.value
    if re.search(r"per\s+month|/month|\bmonthly\b", ctx):
        return CompensationInterval.MONTHLY.value
    if re.search(
        r"per\s+year|per\s+annum|per\s+annually|/year|\bannually\b|p\.?\s*a\.?",
        ctx,
    ):
        return CompensationInterval.YEARLY.value
    return None


def _salary_range_to_result(
    min_salary: int,
    max_salary: int,
    *,
    context: str,
    currency: str,
    lower_limit: int,
    upper_limit: int,
    hourly_threshold: int,
    monthly_threshold: int,
    enforce_annual_salary: bool,
) -> tuple[str | None, int | None, int | None, str | None]:
    def convert_hourly_to_annual(hourly_wage: int) -> int:
        return hourly_wage * 2080

    def convert_monthly_to_annual(monthly_wage: int) -> int:
        return monthly_wage * 12

    interval_override = _salary_interval_from_context(context)
    annual_max_salary: int | None = None

    if interval_override == CompensationInterval.HOURLY.value:
        interval = CompensationInterval.HOURLY.value
        annual_min_salary = convert_hourly_to_annual(min_salary)
        annual_max_salary = convert_hourly_to_annual(max_salary)
    elif interval_override == CompensationInterval.MONTHLY.value:
        interval = CompensationInterval.MONTHLY.value
        annual_min_salary = convert_monthly_to_annual(min_salary)
        annual_max_salary = convert_monthly_to_annual(max_salary)
    elif interval_override == CompensationInterval.YEARLY.value:
        interval = CompensationInterval.YEARLY.value
        annual_min_salary = min_salary
        annual_max_salary = max_salary
    elif min_salary < hourly_threshold:
        interval = CompensationInterval.HOURLY.value
        annual_min_salary = convert_hourly_to_annual(min_salary)
        if max_salary < hourly_threshold:
            annual_max_salary = convert_hourly_to_annual(max_salary)
    elif min_salary < monthly_threshold:
        interval = CompensationInterval.MONTHLY.value
        annual_min_salary = convert_monthly_to_annual(min_salary)
        if max_salary < monthly_threshold:
            annual_max_salary = convert_monthly_to_annual(max_salary)
    else:
        interval = CompensationInterval.YEARLY.value
        annual_min_salary = min_salary
        annual_max_salary = max_salary

    if annual_max_salary is None:
        return None, None, None, None
    if not (
        lower_limit <= annual_min_salary <= upper_limit
        and lower_limit <= annual_max_salary <= upper_limit
        and annual_min_salary <= annual_max_salary
    ):
        return None, None, None, None

    if enforce_annual_salary:
        return interval, annual_min_salary, annual_max_salary, currency
    return interval, min_salary, max_salary, currency


def extract_salary(
    salary_str,
    lower_limit=1000,
    upper_limit=700000,
    hourly_threshold=350,
    monthly_threshold=30000,
    enforce_annual_salary=False,
):
    """
    Extracts salary information from a string and returns the salary interval, min and max salary values, and currency.
    (TODO: Needs test cases as the regex is complicated and may not cover all edge cases)
    """
    if not salary_str:
        return None, None, None, None

    def to_int(s: str) -> int:
        return int(float(s.replace(",", "")))

    def apply_k(amount: int, suffix: str) -> int:
        return amount * 1000 if suffix and "k" in suffix.lower() else amount

    currency_prefix = r"(?:S\$|SGD\s*|\$)\s*"
    amount = r"(\d+(?:,\d+)?(?:\.\d+)?)([kK]?)"
    min_max_pattern = (
        rf"{currency_prefix}{amount}\s*[-—–]\s*(?:S\$|SGD\s*|\$)?\s*{amount}"
    )
    from_pattern = rf"(?:from|up\s+to)\s+{currency_prefix}{amount}"

    for pattern, single_value in ((min_max_pattern, False), (from_pattern, True)):
        match = re.search(pattern, salary_str, re.IGNORECASE)
        if not match:
            continue

        min_salary = apply_k(to_int(match.group(1)), match.group(2))
        if single_value:
            max_salary = min_salary
        else:
            max_salary = apply_k(to_int(match.group(3)), match.group(4))

        context_end = min(len(salary_str), match.end() + 80)
        context = salary_str[match.start() : context_end]
        currency = _salary_currency_from_text(match.group(0))

        result = _salary_range_to_result(
            min_salary,
            max_salary,
            context=context,
            currency=currency,
            lower_limit=lower_limit,
            upper_limit=upper_limit,
            hourly_threshold=hourly_threshold,
            monthly_threshold=monthly_threshold,
            enforce_annual_salary=enforce_annual_salary,
        )
        if result[1] is not None:
            return result

    return None, None, None, None


def extract_job_type(description: str):
    if not description:
        return []

    keywords = {
        JobType.FULL_TIME: r"full\s?time",
        JobType.PART_TIME: r"part\s?time",
        JobType.INTERNSHIP: r"internship",
        JobType.CONTRACT: r"contract",
    }

    listing_types = []
    for key, pattern in keywords.items():
        if re.search(pattern, description, re.IGNORECASE):
            listing_types.append(key)

    return listing_types if listing_types else None


def map_str_to_site(site_name: str) -> Site:
    return Site[site_name.upper()]


def get_enum_from_value(value_str):
    for job_type in JobType:
        if value_str in job_type.value:
            return job_type
    raise Exception(f"Invalid job type: {value_str}")


def convert_to_annual(job_data: dict):
    if job_data["interval"] == "hourly":
        job_data["min_amount"] *= 2080
        job_data["max_amount"] *= 2080
    if job_data["interval"] == "monthly":
        job_data["min_amount"] *= 12
        job_data["max_amount"] *= 12
    if job_data["interval"] == "weekly":
        job_data["min_amount"] *= 52
        job_data["max_amount"] *= 52
    if job_data["interval"] == "daily":
        job_data["min_amount"] *= 260
        job_data["max_amount"] *= 260
    job_data["interval"] = "yearly"


desired_order = [
    "id",
    "site",
    "job_url",
    "job_url_direct",
    "title",
    "company",
    "location",
    "date_posted",
    "job_type",
    "salary_source",
    "interval",
    "min_amount",
    "max_amount",
    "currency",
    "is_remote",
    "job_level",
    "job_function",
    "listing_type",
    "emails",
    "description",
    "company_industry",
    "company_url",
    "company_logo",
    "company_url_direct",
    "company_addresses",
    "company_num_employees",
    "company_revenue",
    "company_description",
    # naukri-specific fields
    "skills",
    "experience_range",
    "company_rating",
    "company_reviews_count",
    "vacancy_count",
    "work_from_home_type",
]
