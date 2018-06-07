# wevote_functions/functions.py
# Brought to you by We Vote. Be good.
# -*- coding: UTF-8 -*-

import datetime
from nameparser import HumanName
import random
import re
import string
import sys
import types
import wevote_functions.admin
import json
import requests
from django.contrib import messages

# We don't want to include the actual constants from organization/models.py, since that can cause include conflicts
CORPORATION = 'C'
GROUP = 'G'  # Group of people (not an individual), but org status unknown
INDIVIDUAL = 'I'  # One person
NONPROFIT = 'NP'
NONPROFIT_501C3 = 'C3'
NONPROFIT_501C4 = 'C4'
NEWS_ORGANIZATION = 'NW'
ORGANIZATION = 'O'  # Deprecated
POLITICAL_ACTION_COMMITTEE = 'P'
PUBLIC_FIGURE = 'PF'
UNKNOWN = 'U'
VOTER = 'V'


logger = wevote_functions.admin.get_logger(__name__)


STATE_CODE_MAP = {
    'AK': 'Alaska',
    'AL': 'Alabama',
    'AR': 'Arkansas',
    'AS': 'American Samoa',
    'AZ': 'Arizona',
    'CA': 'California',
    'CO': 'Colorado',
    'CT': 'Connecticut',
    'DC': 'District of Columbia',
    'DE': 'Delaware',
    'FL': 'Florida',
    'GA': 'Georgia',
    'GU': 'Guam',
    'HI': 'Hawaii',
    'IA': 'Iowa',
    'ID': 'Idaho',
    'IL': 'Illinois',
    'IN': 'Indiana',
    'KS': 'Kansas',
    'KY': 'Kentucky',
    'LA': 'Louisiana',
    'MA': 'Massachusetts',
    'MD': 'Maryland',
    'ME': 'Maine',
    'MI': 'Michigan',
    'MN': 'Minnesota',
    'MO': 'Missouri',
    'MP': 'Northern Mariana Islands',
    'MS': 'Mississippi',
    'MT': 'Montana',
    'NA': 'National',
    'NC': 'North Carolina',
    'ND': 'North Dakota',
    'NE': 'Nebraska',
    'NH': 'New Hampshire',
    'NJ': 'New Jersey',
    'NM': 'New Mexico',
    'NV': 'Nevada',
    'NY': 'New York',
    'OH': 'Ohio',
    'OK': 'Oklahoma',
    'OR': 'Oregon',
    'PA': 'Pennsylvania',
    'PR': 'Puerto Rico',
    'RI': 'Rhode Island',
    'SC': 'South Carolina',
    'SD': 'South Dakota',
    'TN': 'Tennessee',
    'TX': 'Texas',
    'UT': 'Utah',
    'VA': 'Virginia',
    'VI': 'Virgin Islands',
    'VT': 'Vermont',
    'WA': 'Washington',
    'WI': 'Wisconsin',
    'WV': 'West Virginia',
    'WY': 'Wyoming',
}

UTC_OFFSET_MAP = {
    'AK': -32400,
    'AL': -18000,
    'AR': -21600,
    'AS': -39600,
    'AZ': -25200,
    'CA': -28800,
    'CO': -25200,
    'CT': -18000,
    'DC': -18000,
    'DE': -18000,
    'FL': -18000,
    'GA': -18000,
    'GU':  36000,
    'HI': -36000,
    'IA': -21600,
    'ID': -25200,
    'IL': -21600,
    'IN': -18000,
    'KS': -21600,
    'KY': -18000,
    'LA': -21600,
    'MA': -18000,
    'MD': -18000,
    'ME': -18000,
    'MI': -18000,
    'MN': -21600,
    'MO': -21600,
    'MP':  36000,
    'MS': -21600,
    'MT': -25200,
    'NC': -18000,
    'ND': -21600,
    'NE': -21600,
    'NH': -18000,
    'NJ': -18000,
    'NM': -25200,
    'NV': -25200,
    'NY': -18000,
    'OH': -18000,
    'OK': -21600,
    'OR': -25200,
    'PA': -18000,
    'PR': -14400,
    'RI': -18000,
    'SC': -18000,
    'SD': -21600,
    'TN': -18000,
    'TX': -21600,
    'UT': -25200,
    'VA': -18000,
    'VI': -14400,
    'VT': -18000,
    'WA': -28800,
    'WI': -21600,
    'WV': -18000,
    'WY': -25200,
}

POSITIVE_SEARCH_KEYWORDS = [
    "affiliate",
    "candidate",
    "chair",
    "city",
    "civic",
    "council",
    "country",
    "county",
    "democratic",
    "district",
    "elect",
    "endorse",
    "leader",
    "local",
    "municipal",
    "office",
    "official",
    "party",
    "politic",
    "public",
    "represent",
    "running",
    "state",
]

NEGATIVE_SEARCH_KEYWORDS = [
    "available to serve your needs",
    "call us today",
    "complete satisfaction",
    "fake",
    "for our customers",
    "inc.",
    "is a city",
    "musician",
    "our quality work",
    "parody",
    "singer",
    "view the profiles of people named",
    "we guarantee",
]

AMERICAN_INDEPENDENT = 'AMERICAN_INDEPENDENT'
DEMOCRAT = 'DEMOCRAT'
D_R = 'D_R'
ECONOMIC_GROWTH = 'ECONOMIC_GROWTH'
GREEN = 'GREEN'
INDEPENDENT = 'INDEPENDENT'
INDEPENDENT_GREEN = 'INDEPENDENT_GREEN'
LIBERTARIAN = 'LIBERTARIAN'
NO_PARTY_PREFERENCE = 'NO_PARTY_PREFERENCE'
NON_PARTISAN = 'NON_PARTISAN'
PEACE_AND_FREEDOM = 'PEACE_AND_FREEDOM'
REFORM = 'REFORM'
REPUBLICAN = 'REPUBLICAN'

LANGUAGE_CODE_ENGLISH = 'en'
LANGUAGE_CODE_SPANISH = 'es'

# U.S. House California District 33
# UNITED STATES REPRESENTATIVE, 33rd District

OFFICE_NAME_EQUIVALENT_PHRASE_PAIRS = {
    'commissioner of insurance': 'insurance commissioner',
    'member state board of equalization': 'state board of equalization',
    'member of the state assembly': 'state assembly',
    'superintendent of public instruction': 'state superintendent of public instruction',
    'supervisor': 'board of supervisors',
    'united states representative': 'u.s. house',
    'united states senator': 'u.s. senate',
}

# Single digit districts go last, so we can find the double digit districts first
OFFICE_NAME_EQUIVALENT_DISTRICT_PHRASE_PAIRS = {
    'district 10': '10th district',
    'district 11': '11th district',
    'district 12': '12th district',
    'district 13': '13th district',
    'district 14': '14th district',
    'district 15': '15th district',
    'district 16': '16th district',
    'district 17': '17th district',
    'district 18': '18th district',
    'district 19': '19th district',
    '10th congressional district': 'district 10',
    '11th congressional district': 'district 11',
    '12th congressional district': 'district 12',
    '13th congressional district': 'district 13',
    '14th congressional district': 'district 14',
    '15th congressional district': 'district 15',
    '16th congressional district': 'district 16',
    '17th congressional district': 'district 17',
    '18th congressional district': 'district 18',
    '19th congressional district': 'district 19',
    'district 20': '20th district',
    'district 21': '21st district',
    'district 22': '22nd district',
    'district 23': '23rd district',
    'district 24': '24th district',
    'district 25': '25th district',
    'district 26': '26th district',
    'district 27': '27th district',
    'district 28': '28th district',
    'district 29': '29th district',
    '20th congressional district': 'district 20',
    '21st congressional district': 'district 21',
    '22nd congressional district': 'district 22',
    '23th congressional district': 'district 23',
    '24th congressional district': 'district 24',
    '25th congressional district': 'district 25',
    '26th congressional district': 'district 26',
    '27th congressional district': 'district 27',
    '28th congressional district': 'district 28',
    '29th congressional district': 'district 29',
    'district 30': '30th district',
    'district 31': '31st district',
    'district 32': '32nd district',
    'district 33': '33rd district',
    'district 34': '34th district',
    'district 35': '35th district',
    'district 36': '36th district',
    'district 37': '37th district',
    'district 38': '38th district',
    'district 39': '39th district',
    '30th congressional district': 'district 30',
    '31st congressional district': 'district 31',
    '32nd congressional district': 'district 32',
    '33th congressional district': 'district 33',
    '34th congressional district': 'district 34',
    '35th congressional district': 'district 35',
    '36th congressional district': 'district 36',
    '37th congressional district': 'district 37',
    '38th congressional district': 'district 38',
    '39th congressional district': 'district 39',
    'district 40': '40th district',
    'district 41': '41st district',
    'district 42': '42nd district',
    'district 43': '43rd district',
    'district 44': '44th district',
    'district 45': '45th district',
    'district 46': '46th district',
    'district 47': '47th district',
    'district 48': '48th district',
    'district 49': '49th district',
    '40th congressional district': 'district 40',
    '41st congressional district': 'district 41',
    '42nd congressional district': 'district 42',
    '43th congressional district': 'district 43',
    '44th congressional district': 'district 44',
    '45th congressional district': 'district 45',
    '46th congressional district': 'district 46',
    '47th congressional district': 'district 47',
    '48th congressional district': 'district 48',
    '49th congressional district': 'district 49',
    'district 50': '50th district',
    'district 51': '51st district',
    'district 52': '52nd district',
    'district 53': '53rd district',
    'district 54': '54th district',
    'district 55': '55th district',
    'district 56': '56th district',
    'district 57': '57th district',
    'district 58': '58th district',
    'district 59': '59th district',
    '50th congressional district': 'district 50',
    '51st congressional district': 'district 51',
    '52nd congressional district': 'district 52',
    '53th congressional district': 'district 53',
    '54th congressional district': 'district 54',
    '55th congressional district': 'district 55',
    '56th congressional district': 'district 56',
    '57th congressional district': 'district 57',
    '58th congressional district': 'district 58',
    '59th congressional district': 'district 59',
    'district 60': '60th district',
    'district 61': '61st district',
    'district 62': '62nd district',
    'district 63': '63rd district',
    'district 64': '64th district',
    'district 65': '65th district',
    'district 66': '66th district',
    'district 67': '67th district',
    'district 68': '68th district',
    'district 69': '69th district',
    '60th congressional district': 'district 60',
    '61st congressional district': 'district 61',
    '62nd congressional district': 'district 62',
    '63th congressional district': 'district 63',
    '64th congressional district': 'district 64',
    '65th congressional district': 'district 65',
    '66th congressional district': 'district 66',
    '67th congressional district': 'district 67',
    '68th congressional district': 'district 68',
    '69th congressional district': 'district 69',
    'district 70': '70th district',
    'district 71': '71st district',
    'district 72': '72nd district',
    'district 73': '73rd district',
    'district 74': '74th district',
    'district 75': '75th district',
    'district 76': '76th district',
    'district 77': '77th district',
    'district 78': '78th district',
    'district 79': '79th district',
    '70th congressional district': 'district 70',
    '71st congressional district': 'district 71',
    '72nd congressional district': 'district 72',
    '73th congressional district': 'district 73',
    '74th congressional district': 'district 74',
    '75th congressional district': 'district 75',
    '76th congressional district': 'district 76',
    '77th congressional district': 'district 77',
    '78th congressional district': 'district 78',
    '79th congressional district': 'district 79',
    'district 80': '80th district',
    'district 81': '81st district',
    'district 82': '82nd district',
    'district 83': '83rd district',
    'district 84': '84th district',
    'district 85': '85th district',
    'district 86': '86th district',
    'district 87': '87th district',
    'district 88': '88th district',
    'district 89': '89th district',
    'district 90': '90th district',
    '90th congressional district': 'district 90',
    '91st congressional district': 'district 91',
    '92nd congressional district': 'district 92',
    '93th congressional district': 'district 93',
    '94th congressional district': 'district 94',
    '95th congressional district': 'district 95',
    '96th congressional district': 'district 96',
    '97th congressional district': 'district 97',
    '98th congressional district': 'district 98',
    '99th congressional district': 'district 99',
    'district 1': '1st district',
    'district 2': '2nd district',
    'district 3': '3rd district',
    'district 4': '4th district',
    'district 5': '5th district',
    'district 6': '6th district',
    'district 7': '7th district',
    'district 8': '8th district',
    'district 9': '9th district',
    '1st congressional district': 'district 1',
    '2nd congressional district': 'district 2',
    '3rd congressional district': 'district 3',
    '4th congressional district': 'district 4',
    '5th congressional district': 'district 5',
    '6th congressional district': 'district 6',
    '7th congressional district': 'district 7',
    '8th congressional district': 'district 8',
    '9th congressional district': 'district 9',
}

# We also check generate state specific phrases like "of california"
OFFICE_NAME_COMMON_PHRASES_TO_REMOVE_FROM_SEARCHES = [
    "long beach",
    "orange county",
    "san diego",
    "san francisco",
    # "santa clara county",
    # "of santa clara county",
    "(voter nominated)",
]


class LocalSwitch(object):
    def __init__(self, value):
        self.value = value
        self.fall = False

    def __iter__(self):
        """Return the match method once, then stop"""
        yield self.match
        raise StopIteration

    def match(self, *args):
        """Indicate whether or not to enter a case suite"""
        if self.fall or not args:
            return True
        elif self.value in args:  # changed for v1.5, see below
            self.fall = True
            return True
        else:
            return False


# This is how we make sure a variable is a boolean
def convert_to_bool(value):
    if value is True:
        return True
    elif value is 1:
        return True
    elif value > 0:
        return True
    elif value is False:
        return False
    elif value is 0:
        return True
    elif value is None:
        return False

    value = value.lower()
    if value in ['true', '1']:
        return True
    elif value in ['false', '0']:
        return False
    return False


# This is how we make sure a variable is float
def convert_to_float(value):
    # Catch the cases where the incoming value is None
    if value is None:
        return 0.0
    try:
        new_value = float(value)
    except ValueError:
        new_value = 0.0
    return new_value


# This is how we make sure a variable is an integer
def convert_to_int(value):
    # Catch the cases where the incoming value is None
    if value is None:
        return 0
    try:
        new_value = int(value)
    except ValueError:
        new_value = 0
    return new_value


# This is how we make sure a variable is a string
def convert_to_str(value):
    # Catch the cases where the incoming value is None
    if value is None:
        return ""
    try:
        new_value = str(value)
    except ValueError:
        new_value = ''
    return new_value


# See also 'candidate_party_display' in candidate/models.py
def convert_to_political_party_constant(raw_party_incoming):
    if not positive_value_exists(raw_party_incoming):
        return ""

    raw_party = raw_party_incoming.strip()
    raw_party = raw_party.lower()
    raw_party = raw_party.replace("Party Preference: ", "")

    if raw_party == 'amer. ind.':
        return AMERICAN_INDEPENDENT
    if raw_party == 'american independent':
        return AMERICAN_INDEPENDENT
    if raw_party == 'dem':
        return DEMOCRAT
    if raw_party == 'democrat':
        return DEMOCRAT
    if raw_party == 'democratic':
        return DEMOCRAT
    if raw_party == 'democratic party':
        return DEMOCRAT
    if raw_party == 'd-r party':
        return D_R
    if raw_party == 'economic growth':
        return ECONOMIC_GROWTH
    if raw_party == 'grn':
        return GREEN
    if raw_party == 'green':
        return GREEN
    if raw_party == 'green party':
        return GREEN
    if raw_party == 'independent':
        return INDEPENDENT
    if raw_party == 'independent green':
        return INDEPENDENT_GREEN
    if raw_party == 'lib':
        return LIBERTARIAN
    if raw_party == 'Libertarian':
        return LIBERTARIAN
    if raw_party == 'npp':
        return NO_PARTY_PREFERENCE
    if raw_party == 'no party preference':
        return NO_PARTY_PREFERENCE
    if raw_party == 'non-partisan':
        return NON_PARTISAN
    if raw_party == 'nonpartisan':
        return NON_PARTISAN
    if raw_party == 'pf':
        return PEACE_AND_FREEDOM
    if raw_party == 'peace and freedom':
        return PEACE_AND_FREEDOM
    if raw_party == 'reform':
        return REFORM
    if raw_party == 'rep':
        return REPUBLICAN
    if raw_party == 'republican':
        return REPUBLICAN
    if raw_party == 'republican party':
        return REPUBLICAN
    else:
        return raw_party_incoming


def convert_date_to_date_as_integer(date):
    day_as_string = "{:d}{:02d}{:02d}".format(
        date.year,
        date.month,
        date.day,
    )
    return convert_to_int(day_as_string)


def extract_state_from_ocd_division_id(ocd_division_id):
    # Pull this from ocdDivisionId
    pieces = [piece.split(':', 1) for piece in ocd_division_id.split('/')]
    fields = {}

    # if it included the ocd-division bit, pop it off
    if pieces[0] == ['ocd-division']:
        pieces.pop(0)

    if pieces[0][0] != 'country':
        # raise ValueError('OCD id must start with country')
        return ''
    fields['country'] = pieces[0][1]

    if len(pieces) < 2:
        return ''

    if pieces[1][0] != 'state':
        # raise ValueError('Expecting state from OCD, and state not found')
        return ''

    fields['state'] = pieces[1][1]

    return fields['state']


def extract_state_code_from_address_string(text_for_map_search):
    text_for_map_search_lower = text_for_map_search.lower()
    text_for_map_search_substring_list = re.split(r'[;,\s]\s*', text_for_map_search_lower)
    for state_code, state_name in STATE_CODE_MAP.items():
        if state_code.lower() in text_for_map_search_substring_list:
            return state_code.lower()
        elif state_name.lower() in text_for_map_search_substring_list:
            return state_code.lower()

    return ""


def extract_district_from_ocd_division_id(ocd_division_id):
    # Pull this from ocdDivisionId
    pieces = [piece.split(':', 1) for piece in ocd_division_id.split('/')]
    fields = {}

    # if it included the ocd-division bit, pop it off
    if pieces[0] == ['ocd-division']:
        pieces.pop(0)

    if pieces[0][0] != 'country':
        # raise ValueError('OCD id must start with country')
        return ''
    fields['country'] = pieces[0][1]

    if len(pieces) < 2:
        return ''

    if pieces[1][0] != 'district':
        # raise ValueError('Expecting state from OCD, and district not found')
        return ''

    fields['district'] = pieces[1][1]

    return fields['district']


def extract_zip5_from_zip9(zip9):
    zip5_text = zip9[0:5]
    if len(zip5_text) == 5:
        return zip5_text
    elif len(zip5_text) == 4:
        return '0' + zip5_text
    elif len(zip5_text) == 3:
        return '00' + zip5_text
    return zip5_text


def extract_zip4_from_zip9(zip9):
    if len(zip9) <= 5:
        return ''
    elif len(zip9) == 9:
        # Return characters 6-9
        return zip9[5:9]
    return ''


def extract_zip_formatted_from_zip9(zip9):
    formatted_zip_text = extract_zip5_from_zip9(zip9)
    if len(extract_zip4_from_zip9(zip9)) == 4:
        formatted_zip_text += '-' + extract_zip4_from_zip9(zip9)

    return formatted_zip_text


def display_full_name_with_correct_capitalization(full_name):
    """
    See documentation here: https://github.com/derek73/python-nameparser
    :param full_name:
    :return:
    """
    if full_name is not None and not callable(full_name):
        full_name = str(full_name)
        full_name.strip()
        full_name_parsed = HumanName(full_name)
        full_name_parsed.capitalize()
        full_name_capitalized = str(full_name_parsed)
        return full_name_capitalized
    return ""


def extract_email_addresses_from_string(incoming_string):
    """
    Thanks to https://gist.github.com/dideler/5219706
    :param incoming_string:
    :return:
    """
    string_lower_case = incoming_string.lower()
    regex = re.compile(("([a-z0-9!#$%&'*+\/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+\/=?^_`"
                        "{|}~-]+)*(@|\sat\s)(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(\.|"
                        "\sdot\s))+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)"))

    collection_of_emails = (email[0] for email in re.findall(regex, string_lower_case) if not email[0].startswith('//'))

    list_of_emails = []
    for email in collection_of_emails:
        list_of_emails.append(email)

    return list_of_emails


def extract_title_from_full_name(full_name):
    """
    See documentation here: https://github.com/derek73/python-nameparser
    :param full_name:
    :return:
    """
    if full_name is not None and not callable(full_name):
        full_name = str(full_name)
        full_name.strip()
        full_name_parsed = HumanName(full_name)
        title = full_name_parsed.title
        return title
    return ""


def extract_first_name_from_full_name(full_name):
    """
    See documentation here: https://github.com/derek73/python-nameparser
    :param full_name:
    :return:
    """
    if full_name is not None and not callable(full_name):
        full_name = str(full_name)
        full_name.strip()
        full_name_parsed = HumanName(full_name)
        first_name = full_name_parsed.first
        return first_name
    return ""


def extract_middle_name_from_full_name(full_name):
    """
    See documentation here: https://github.com/derek73/python-nameparser
    :param full_name:
    :return:
    """
    if full_name is not None and not callable(full_name):
        full_name = str(full_name)
        full_name.strip()
        full_name_parsed = HumanName(full_name)
        middle_name = full_name_parsed.middle
        return middle_name
    return ""


def extract_last_name_from_full_name(full_name):
    """
    See documentation here: https://github.com/derek73/python-nameparser
    :param full_name:
    :return:
    """
    if full_name is not None and not callable(full_name):
        full_name = str(full_name)
        full_name.strip()
        full_name_parsed = HumanName(full_name)
        last_name = full_name_parsed.last
        return last_name
    return ""


def extract_suffix_from_full_name(full_name):
    """
    See documentation here: https://github.com/derek73/python-nameparser
    :param full_name:
    :return:
    """
    if full_name is not None and not callable(full_name):
        full_name = str(full_name)
        full_name.strip()
        full_name_parsed = HumanName(full_name)
        suffix = full_name_parsed.suffix
        return suffix
    return ""


def extract_nickname_from_full_name(full_name):
    """
    See documentation here: https://github.com/derek73/python-nameparser
    :param full_name:
    :return:
    """
    if full_name is not None and not callable(full_name):
        full_name = str(full_name)
        full_name.strip()
        full_name_parsed = HumanName(full_name)
        nickname = full_name_parsed.nickname
        return nickname
    return ""


def extract_website_from_url(url_string):
    """

    :param url_string:
    :return:
    """
    if not url_string:
        return ""
    if not positive_value_exists(url_string):
        return ""
    url_string = str(url_string)
    url_string.strip()
    url_string = url_string.replace("https://www.", "")
    url_string = url_string.replace("http://www.", "")
    url_string = url_string.replace("https://", "")
    url_string = url_string.replace("http://", "")
    url_string = url_string.replace("www://", "")
    url_string = url_string.split("/")[0]
    return url_string


def extract_facebook_username_from_text_string(facebook_text_string):
    """

    :param facebook_text_string:
    :return:
    """
    if not facebook_text_string:
        return ""
    if not positive_value_exists(facebook_text_string):
        return ""
    facebook_text_string = str(facebook_text_string)
    facebook_text_string.strip()
    facebook_text_string = facebook_text_string.lower()
    facebook_text_string = facebook_text_string.replace("http://facebook.com", "")
    facebook_text_string = facebook_text_string.replace("http://www.facebook.com", "")
    facebook_text_string = facebook_text_string.replace("http://m.facebook.com", "")
    facebook_text_string = facebook_text_string.replace("https://facebook.com", "")
    facebook_text_string = facebook_text_string.replace("https://www.facebook.com", "")
    facebook_text_string = facebook_text_string.replace("https://m.facebook.com", "")
    facebook_text_string = facebook_text_string.replace("www.facebook.com", "")
    facebook_text_string = facebook_text_string.replace("facebook.com", "")
    facebook_text_string = facebook_text_string.replace("@", "")
    facebook_text_string = facebook_text_string.replace("/", "")
    facebook_text_string = facebook_text_string.split("?", 1)[0]  # Remove everything after first "?" (including "?")
    return facebook_text_string


def extract_twitter_handle_from_text_string(twitter_text_string):
    """

    :param twitter_text_string:
    :return:
    """
    if not twitter_text_string:
        return ""
    if not positive_value_exists(twitter_text_string):
        return ""
    twitter_text_string = str(twitter_text_string)
    twitter_text_string.strip()
    twitter_text_string = twitter_text_string.lower()
    twitter_text_string = twitter_text_string.replace("http://twitter.com", "")
    twitter_text_string = twitter_text_string.replace("http://www.twitter.com", "")
    twitter_text_string = twitter_text_string.replace("http://m.twitter.com", "")
    twitter_text_string = twitter_text_string.replace("https://twitter.com", "")
    twitter_text_string = twitter_text_string.replace("https://m.twitter.com", "")
    twitter_text_string = twitter_text_string.replace("https://www.twitter.com", "")
    twitter_text_string = twitter_text_string.replace("www.twitter.com", "")
    twitter_text_string = twitter_text_string.replace("twitter.com", "")
    twitter_text_string = twitter_text_string.replace("@", "")
    twitter_text_string = twitter_text_string.replace("/", "")
    twitter_text_string = twitter_text_string.split("?", 1)[0]  # Remove everything after first "?" (including "?")
    return twitter_text_string


def get_ip_from_headers(request):
    x_forwarded_for = request.META.get('X-Forwarded-For')
    http_x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[-1].strip()
    elif http_x_forwarded_for:
        return http_x_forwarded_for.split(',')[0].strip()
    else:
        return request.META.get('REMOTE_ADDR')


def get_maximum_number_to_retrieve_from_request(request):
    if 'maximum_number_to_retrieve' in request.GET:
        maximum_number_to_retrieve = request.GET['maximum_number_to_retrieve']
    else:
        maximum_number_to_retrieve = 0
    if maximum_number_to_retrieve is "":
        maximum_number_to_retrieve = 0
    else:
        maximum_number_to_retrieve = convert_to_int(maximum_number_to_retrieve)

    return maximum_number_to_retrieve


# http://stackoverflow.com/questions/1622793/django-cookies-how-can-i-set-them
def set_cookie(response, cookie_name, cookie_value, days_expire=None):
    if days_expire is None:
        max_age = 10 * 365 * 24 * 60 * 60  # ten years
    else:
        max_age = days_expire * 24 * 60 * 60
    expires = datetime.datetime.strftime(datetime.datetime.utcnow() + datetime.timedelta(seconds=max_age),
                                         "%a, %d-%b-%Y %H:%M:%S GMT")
    response.set_cookie(cookie_name, cookie_value, max_age=max_age, expires=expires, path="/")


def delete_cookie(response, cookie_name):
    response.delete_cookie(cookie_name, path="/")


def get_voter_api_device_id(request, generate_if_no_cookie=False):
    """
    This function retrieves the voter_api_device_id from the cookies on API server
    :param request:
    :param generate_if_no_cookie:
    :return:
    """
    voter_api_device_id = ''
    if 'voter_api_device_id' in request.COOKIES:
        voter_api_device_id = request.COOKIES['voter_api_device_id']
        logger.debug("from cookie, voter_api_device_id: {voter_api_device_id}".format(
            voter_api_device_id=voter_api_device_id
        ))
    if voter_api_device_id == '' and generate_if_no_cookie:
        voter_api_device_id = generate_voter_device_id()  # Stored in cookie below
        logger.debug("generate_voter_device_id, voter_api_device_id: {voter_api_device_id}".format(
            voter_api_device_id=voter_api_device_id
        ))
    return voter_api_device_id


def get_voter_device_id(request, generate_if_no_value=False):
    """
    This function retrieves the voter_device_id from the GET values coming from a client
    :param request:
    :param generate_if_no_value:
    :return:
    """
    # First check the headers
    voter_device_id = request.META.get('HTTP_X_HEADER_DEVICEID', '')
    if positive_value_exists(voter_device_id):
        return voter_device_id

    # Then check for incoming GET value
    voter_device_id = request.GET.get('voter_device_id', '')
    if positive_value_exists(voter_device_id):
        return voter_device_id

    # Then check for a cookie (in Native)
    if 'voter_device_id' in request.COOKIES:
        return request.COOKIES['voter_device_id']

    if generate_if_no_value:
        voter_device_id = generate_voter_device_id()
        logger.debug("generate_voter_device_id, voter_device_id: {voter_device_id}".format(
            voter_device_id=voter_device_id
        ))
        return voter_device_id
    else:
        return ''


def is_link_to_video(link_url):
    if link_url is None:
        return False
    if "youtube.com" in link_url:
        return True
    return False


def is_speaker_type_individual(speaker_type):
    if speaker_type in (INDIVIDUAL, VOTER):
        return True
    return False


def is_speaker_type_organization(speaker_type):
    if speaker_type in (CORPORATION, GROUP, NEWS_ORGANIZATION, NONPROFIT, NONPROFIT_501C3,
                        NONPROFIT_501C4, ORGANIZATION, POLITICAL_ACTION_COMMITTEE, "ORGANIZATION"):
        return True
    return False


def is_speaker_type_public_figure(speaker_type):
    if speaker_type in (PUBLIC_FIGURE, "PUBLIC_FIGURE"):
        return True
    return False


def is_voter_device_id_valid(voter_device_id):
    if not voter_device_id \
            or len(voter_device_id) <= 70 \
            or len(voter_device_id) >= 90:
        success = False
        status = "VALID_VOTER_DEVICE_ID_MISSING"
        json_data = {
            'status': status,
            'success': False,
            'voter_device_id': voter_device_id,
        }
    else:
        success = True
        status = "VALID_VOTER_DEVICE_ID_FOUND"
        json_data = {
            'status': status,
            'success': True,
            'voter_device_id': voter_device_id,
        }

    results = {
        'status': status,
        'success': success,
        'json_data': json_data,
    }
    return results


# TODO: To be deprecated since we don't want to set voter_device_id locally to the API server
def set_voter_device_id(request, response, voter_device_id):
    if 'voter_device_id' not in request.COOKIES:
        set_cookie(response, 'voter_device_id', voter_device_id)


def set_voter_api_device_id(request, response, voter_api_device_id):
    if 'voter_api_device_id' not in request.COOKIES:
        set_cookie(response, 'voter_api_device_id', voter_api_device_id)


def delete_voter_api_device_id_cookie(response):
    delete_cookie(response, 'voter_api_device_id')


def generate_random_string(string_length=88, chars=string.ascii_lowercase + string.ascii_uppercase + string.digits):
    """
    Generate a random string.
    :param string_length:
    :param chars:
    :return:
    """
    return ''.join(random.SystemRandom().choice(chars) for _ in range(string_length))


def generate_voter_device_id():
    """

    :return:
    :test: WeVoteAPIsV1TestsDeviceIdGenerate
    """
    # We would like this device_id to be long so hackers can't cycle through all possible device ids to get access to
    # a voter's sign in session. As of this writing, all 8 digit strings can be cracked locally in 5.5 hours given the
    # right hardware:
    # http://arstechnica.com/security/2012/12/25-gpu-cluster-cracks-every-standard-windows-password-in-6-hours/
    # But there are limits to how much cookie real-estate every site has.
    # See: http://browsercookielimits.squawky.net/ If you use characters only in the ASCII range, each character
    # takes 1 byte, so you can typically store 4096 characters
    # We use 88 characters to secure us for the foreseeable future, which gives us a unique identifier space of
    # 2.79 with 124 zeros after it
    #  26 + 26 + 10 = 62 character options per "digit"
    #  88(62) = 2.798279e+124
    new_device_id = generate_random_string(88)

    # We do not currently check that this device_id is already in the database because it is such a large number space
    return new_device_id


def positive_value_exists(value):
    """
    This is a test to see if a positive value exists. All of these return false:
        "" (an empty string)
        0 (0 as an integer)
        -1
        0.0 (0 as a float)
        "0" (0 as a string)
        NULL
        FALSE
        array() (an empty array)
    :param value:
    :return: bool
    """
    try:
        if value in [None, '', 'None', False, 'FALSE', 'False', 'false', '0']:
            return False
        if value in ['TRUE', 'True', 'true', '1']:
            return True
        if sys.version_info > (3, 0):
            # Python 3 code in this block
            if isinstance(value, list):
                return bool(len(value))
            if isinstance(value, dict):
                return bool(len(value))
            if isinstance(value, datetime.date):
                return bool(value is not None)
            if isinstance(value, str):
                return bool(len(value))
        else:
            # Python 2 code in this block
            if isinstance(value, types.ListType):
                return bool(len(value))
            if isinstance(value, types.DictType):
                return bool(len(value))
            try:
                basestring
            except NameError:
                basestring = str
            if isinstance(value, basestring):
                return bool(len(value))
            # TODO We aren't checking for datetime format and need to

        value = float(value)
        if value <= 0:
            return False
    except ValueError:
        pass
    return bool(value)


def convert_state_text_to_state_code(state_text):
    for state_code, state_name in STATE_CODE_MAP.items():
        if state_text.lower() == state_name.lower():
            return state_code
    else:
        return ""


def convert_state_code_to_state_text(incoming_state_code):
    for state_code, state_name in STATE_CODE_MAP.items():
        if incoming_state_code.lower() == state_code.lower():
            return state_name
    else:
        return ""


def convert_state_code_to_utc_offset(state_code):
    return UTC_OFFSET_MAP.get(state_code, None)


def process_request_from_master(request, message_text, get_url, get_params):
    """

    :param request:
    :param message_text:
    :param get_url:
    :param get_params:
    :return: structured_json and import_results
    """
    if 'google_civic_election_id' in get_params:
        message_text += " for google_civic_election_id " + str(get_params['google_civic_election_id'])
    messages.add_message(request, messages.INFO, message_text)
    logger.info(message_text)
    print(message_text)  # Please don't remove this line

    response = requests.get(get_url, params=get_params)

    structured_json = json.loads(response.text)
    if 'success' in structured_json and not structured_json['success']:
        import_results = {
            'success': False,
            'status': "Error: " + structured_json['status'],
        }
    else:
        import_results = {
            'success': True,
            'status': "",
        }

    if 'google_civic_election_id' in get_params:
        print("... the master server returned " + str(len(structured_json)) + " items.  Election " +
              str(get_params['google_civic_election_id']))  # Please don't remove this line
    else:
        print("... the master server returned " + str(len(structured_json)) + " items.") # Please don't remove this line

    return import_results, structured_json
