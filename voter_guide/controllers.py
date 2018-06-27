# voter_guide/controllers.py
# Brought to you by We Vote. Be good.
# -*- coding: UTF-8 -*-

from ballot.models import OFFICE, CANDIDATE, MEASURE
from candidate.models import CandidateCampaignManager, CandidateCampaignListManager
from config.base import get_environment_variable
from django.http import HttpResponse
from follow.models import FollowOrganizationList, FollowIssueList, FOLLOWING
from itertools import chain
from issue.models import OrganizationLinkToIssueList
import json
from organization.controllers import organization_follow_or_unfollow_or_ignore, \
    push_organization_data_to_other_table_caches, \
    refresh_organization_data_from_master_tables
from organization.models import OrganizationManager, OrganizationListManager
from pledge_to_vote.models import PledgeToVoteManager
from position.controllers import retrieve_ballot_item_we_vote_ids_for_organizations_to_follow
from position.models import ANY_STANCE, INFORMATION_ONLY, OPPOSE, \
    PositionEntered, PositionManager, PositionListManager, SUPPORT
from voter.models import fetch_voter_id_from_voter_device_link, fetch_voter_we_vote_id_from_voter_device_link, \
    fetch_voter_we_vote_id_from_voter_id, VoterManager
from voter_guide.models import VoterGuide, VoterGuideListManager, VoterGuideManager, VoterGuidePossibilityManager
import wevote_functions.admin
from wevote_functions.functions import convert_to_int, is_voter_device_id_valid, positive_value_exists, \
    process_request_from_master, is_link_to_video

logger = wevote_functions.admin.get_logger(__name__)

WE_VOTE_API_KEY = get_environment_variable("WE_VOTE_API_KEY")
VOTER_GUIDES_SYNC_URL = get_environment_variable("VOTER_GUIDES_SYNC_URL")  # voterGuidesSyncOut
CANDIDATE_NUMBER_LIST = ["001", "002", "003", "004"]


def convert_list_of_names_to_possible_candidates(ballot_items_list, google_civic_election_id):
    status = ""
    success = True
    possible_candidate_list = []
    possible_candidate_list_found = False
    candidate_number_list = CANDIDATE_NUMBER_LIST

    number_index = 0
    for one_name in ballot_items_list:
        if number_index >= len(candidate_number_list):
            break
        if not positive_value_exists(one_name):
            continue
        possible_candidate = {
            'candidate_name': one_name,
            'candidate_we_vote_id': "",
            'stance_about_candidate': "SUPPORT",
            'comment_about_candidate': "",
            'possible_candidate_number': candidate_number_list[number_index]
        }
        possible_candidate_list.append(possible_candidate)
        number_index += 1

    if len(possible_candidate_list):
        possible_candidate_list_found = True

    results = {
        'status':                           status,
        'success':                          success,
        'possible_candidate_list':          possible_candidate_list,
        'possible_candidate_list_found':    possible_candidate_list_found,
    }
    return results


def extract_position_list_from_voter_guide_possibility(voter_guide_possibility):
    status = ""
    success = True
    position_json_list = []
    position_json_list_found = False
    candidate_number_list = CANDIDATE_NUMBER_LIST

    google_civic_election_id = voter_guide_possibility.google_civic_election_id \
        if positive_value_exists(voter_guide_possibility.google_civic_election_id) else 0
    # We might want to move to a link per position
    more_info_url = voter_guide_possibility.voter_guide_possibility_url
    organization_name = voter_guide_possibility.organization_name \
        if positive_value_exists(voter_guide_possibility.organization_name) else ""
    organization_we_vote_id = voter_guide_possibility.organization_we_vote_id \
        if positive_value_exists(voter_guide_possibility.organization_we_vote_id) else ""
    organization_twitter_handle = voter_guide_possibility.organization_twitter_handle \
        if positive_value_exists(voter_guide_possibility.organization_twitter_handle) else ""
    state_code = voter_guide_possibility.state_code \
        if positive_value_exists(voter_guide_possibility.state_code) else ""
    number_index = 0
    for candidate_number in candidate_number_list:
        if number_index >= len(candidate_number_list):
            break
        if positive_value_exists(getattr(voter_guide_possibility,
                                         'candidate_name_' + candidate_number)) \
                or positive_value_exists(getattr(voter_guide_possibility,
                                         'candidate_we_vote_id_' + candidate_number)) \
                or positive_value_exists(getattr(voter_guide_possibility,
                                         'comment_about_candidate_' + candidate_number)):
            candidate_name = getattr(voter_guide_possibility, 'candidate_name_' + candidate_number)
            candidate_we_vote_id = getattr(voter_guide_possibility, 'candidate_we_vote_id_' + candidate_number)
            stance = getattr(voter_guide_possibility, 'stance_about_candidate_' + candidate_number)
            statement_text = getattr(voter_guide_possibility, 'comment_about_candidate_' + candidate_number)
            position_json = {
                # 'position_we_vote_id': 'position_we_vote_id',
                'candidate_name': candidate_name,
                'candidate_we_vote_id': candidate_we_vote_id,
                # 'candidate_twitter_handle': 'candidate_twitter_handle',
                # 'contest_office_name': 'contest_office_name',
                # 'contest_measure_title': 'contest_measure_title',
                # 'election_day': election_day,
                # 'grade_rating': 'grade_rating',
                'google_civic_election_id': google_civic_election_id,
                'more_info_url': more_info_url,
                'stance': stance,
                # 'support': 'support',
                # 'oppose': 'oppose',
                # 'percent_rating': 'percent_rating',
                'statement_text': statement_text,
                'state_code': state_code,
                'organization_name': organization_name,
                'organization_we_vote_id': organization_we_vote_id,
                'organization_twitter_handle': organization_twitter_handle,
            }
            position_json_list.append(position_json)
        number_index += 1

    if len(position_json_list):
        position_json_list_found = True

    results = {
        'status':                   status,
        'success':                  success,
        'position_json_list':       position_json_list,
        'position_json_list_found': position_json_list_found,
    }
    return results


def extract_possible_candidate_list_from_database(voter_guide_possibility):
    status = ""
    success = True
    possible_candidate_list = []
    possible_candidate_list_found = False
    candidate_number_list = CANDIDATE_NUMBER_LIST

    number_index = 0
    for candidate_number in candidate_number_list:
        if number_index >= len(candidate_number_list):
            break
        if positive_value_exists(getattr(voter_guide_possibility,
                                         'candidate_name_' + candidate_number_list[number_index])) \
                or positive_value_exists(getattr(voter_guide_possibility,
                                         'candidate_we_vote_id_' + candidate_number_list[number_index])) \
                or positive_value_exists(getattr(voter_guide_possibility,
                                         'comment_about_candidate_' + candidate_number_list[number_index])):
            possible_candidate = {
                'candidate_name':
                getattr(voter_guide_possibility, 'candidate_name_' + candidate_number_list[number_index]),
                'candidate_we_vote_id':
                getattr(voter_guide_possibility, 'candidate_we_vote_id_' + candidate_number_list[number_index]),
                'stance_about_candidate':
                getattr(voter_guide_possibility, 'stance_about_candidate_' + candidate_number_list[number_index]),
                'comment_about_candidate':
                getattr(voter_guide_possibility, 'comment_about_candidate_' + candidate_number_list[number_index]),
                'possible_candidate_number': candidate_number,
            }
            possible_candidate_list.append(possible_candidate)
        number_index += 1

    if len(possible_candidate_list):
        possible_candidate_list_found = True

    results = {
        'status':                           status,
        'success':                          success,
        'possible_candidate_list':          possible_candidate_list,
        'possible_candidate_list_found':    possible_candidate_list_found,
    }
    return results


def match_candidate_list_with_candidates_in_database(possible_candidate_list, google_civic_election_id, state_code=''):
    status = ""
    success = True
    possible_candidate_list_found = False

    possible_candidate_list_modified = []
    candidate_campaign_manager = CandidateCampaignManager()
    candidate_campaign_list_manager = CandidateCampaignListManager()
    for possible_candidate in possible_candidate_list:
        if 'candidate_we_vote_id' in possible_candidate \
                and positive_value_exists(possible_candidate['candidate_we_vote_id']):
            results = candidate_campaign_manager.retrieve_candidate_campaign_from_we_vote_id(
                possible_candidate['candidate_we_vote_id'])
            if results['candidate_campaign_found']:
                possible_candidate['candidate'] = results['candidate_campaign']
                possible_candidate['candidate_name'] = possible_candidate['candidate'].display_candidate_name()
            possible_candidate_list_modified.append(possible_candidate)
        elif 'candidate_name' in possible_candidate and positive_value_exists(possible_candidate['candidate_name']):
            # If here search for possible candidate matches
            matching_results = candidate_campaign_list_manager.retrieve_candidates_from_non_unique_identifiers(
                google_civic_election_id, state_code, '', possible_candidate['candidate_name'])

            if matching_results['candidate_found']:
                candidate = matching_results['candidate']

                # If one candidate found, add we_vote_id here
                possible_candidate['candidate_we_vote_id'] = candidate.we_vote_id
                possible_candidate['candidate'] = candidate
                possible_candidate['candidate_name'] = candidate.display_candidate_name()
                possible_candidate_list_modified.append(possible_candidate)
            elif matching_results['multiple_entries_found']:
                status += "MULTIPLE_CANDIDATES_FOUND "
                possible_candidate_list_modified.append(possible_candidate)
            elif not positive_value_exists(matching_results['success']):
                status += "RETRIEVE_CANDIDATE_FROM_NON_UNIQUE-NO_SUCCESS "
                status += matching_results['status']
                possible_candidate_list_modified.append(possible_candidate)
            else:
                status += "RETRIEVE_CANDIDATE_FROM_NON_UNIQUE-CANDIDATE_NOT_FOUND "
                possible_candidate_list_modified.append(possible_candidate)

    if len(possible_candidate_list):
        possible_candidate_list_found = True

    results = {
        'status':                           status,
        'success':                          success,
        'possible_candidate_list':          possible_candidate_list_modified,
        'possible_candidate_list_found':    possible_candidate_list_found,
    }
    return results


def take_in_possible_candidate_list_from_form(request, google_civic_election_id):
    status = ""
    success = True
    possible_candidate_list = []
    possible_candidate_list_found = False
    candidate_number_list = CANDIDATE_NUMBER_LIST

    number_index = 0
    for candidate_number in candidate_number_list:
        if number_index >= len(candidate_number_list):
            break
        if positive_value_exists(request.POST.get('candidate_name_' + candidate_number_list[number_index], 0)) \
                or positive_value_exists(request.POST.get(
                            'candidate_we_vote_id_' + candidate_number_list[number_index], 0)) \
                or positive_value_exists(request.POST.get(
                            'comment_about_candidate_' + candidate_number_list[number_index], 0)):
            possible_candidate = {
                'candidate_name':
                request.POST.get('candidate_name_' + candidate_number_list[number_index], ""),
                'candidate_we_vote_id':
                request.POST.get('candidate_we_vote_id_' + candidate_number_list[number_index], ""),
                'stance_about_candidate':
                request.POST.get('stance_about_candidate_' + candidate_number_list[number_index], ""),
                'comment_about_candidate':
                request.POST.get('comment_about_candidate_' + candidate_number_list[number_index], ""),
                'possible_candidate_number': candidate_number,
            }
            possible_candidate_list.append(possible_candidate)
        number_index += 1

    if len(possible_candidate_list):
        possible_candidate_list_found = True

    results = {
        'status':                           status,
        'success':                          success,
        'possible_candidate_list':          possible_candidate_list,
        'possible_candidate_list_found':    possible_candidate_list_found,
    }
    return results


def duplicate_voter_guides(from_voter_id, from_voter_we_vote_id, from_organization_we_vote_id,
                           to_voter_id, to_voter_we_vote_id, to_organization_we_vote_id):
    status = ''
    success = False
    voter_guides_duplicated = 0
    voter_guides_not_duplicated = 0
    organization_manager = OrganizationManager()
    voter_guide_list_manager = VoterGuideListManager()
    voter_guide_manager = VoterGuideManager()
    voter_guide_list = voter_guide_list_manager.retrieve_all_voter_guides_by_voter_id(from_voter_id)

    for from_voter_guide in voter_guide_list:
        # TODO When we want to heal the data
        # try:
        #     from_voter_guide.save()
        # except Exception as e:
        #     pass

        # See if the "to_voter_organization" already has an entry for this organization
        voter_guide_id = 0
        voter_guide_we_vote_id = ""
        google_civic_election_id = 0
        vote_smart_time_span = None
        public_figure_we_vote_id = None
        existing_entry_results = voter_guide_manager.retrieve_voter_guide(
            voter_guide_id, voter_guide_we_vote_id, google_civic_election_id, vote_smart_time_span,
            to_organization_we_vote_id, public_figure_we_vote_id, to_voter_we_vote_id)
        if not existing_entry_results['voter_guide_found']:
            try:
                from_voter_guide.id = None  # Reset the id so a new entry is created
                from_voter_guide.pk = None
                from_voter_guide.we_vote_id = None  # Clear out existing we_vote_id
                from_voter_guide.generate_new_we_vote_id()
                # Now replace with to_voter info
                from_voter_guide.owner_voter_id = to_voter_id
                from_voter_guide.owner_voter_we_vote_id = to_voter_we_vote_id
                from_voter_guide.organization_we_vote_id = to_organization_we_vote_id
                from_voter_guide.save()
                voter_guides_duplicated += 1
            except Exception as e:
                voter_guides_not_duplicated += 1

    # Now retrieve by organization_we_vote_id in case there is damaged data
    voter_guide_list = voter_guide_list_manager.retrieve_all_voter_guides_by_organization_we_vote_id(
        from_organization_we_vote_id)

    for from_voter_guide in voter_guide_list:
        # TODO When we want to heal the data
        # try:
        #     from_voter_guide.save()
        # except Exception as e:
        #     pass

        # See if the "to_voter_organization" already has an entry for this organization
        voter_guide_id = 0
        voter_guide_we_vote_id = ""
        google_civic_election_id = 0
        vote_smart_time_span = None
        public_figure_we_vote_id = None
        existing_entry_results = voter_guide_manager.retrieve_voter_guide(
            voter_guide_id, voter_guide_we_vote_id, google_civic_election_id, vote_smart_time_span,
            to_organization_we_vote_id, public_figure_we_vote_id, to_voter_we_vote_id)
        if not existing_entry_results['voter_guide_found']:
            try:
                from_voter_guide.id = None  # Reset the id so a new entry is created
                from_voter_guide.pk = None
                from_voter_guide.we_vote_id = None  # Clear out existing we_vote_id
                from_voter_guide.generate_new_we_vote_id()
                # Now replace with to_voter info
                from_voter_guide.owner_voter_id = to_voter_id
                from_voter_guide.owner_voter_we_vote_id = to_voter_we_vote_id
                from_voter_guide.organization_we_vote_id = to_organization_we_vote_id
                from_voter_guide.save()
                voter_guides_duplicated += 1
            except Exception as e:
                voter_guides_not_duplicated += 1

    results = {
        'status':                       status,
        'success':                      success,
        'from_voter_id':                from_voter_id,
        'from_voter_we_vote_id':        from_voter_we_vote_id,
        'to_voter_id':                  to_voter_id,
        'to_voter_we_vote_id':          to_voter_we_vote_id,
        'voter_guides_duplicated':      voter_guides_duplicated,
        'voter_guides_not_duplicated':  voter_guides_not_duplicated,
    }
    return results


def move_voter_guides_to_another_voter(from_voter_we_vote_id, to_voter_we_vote_id,
                                       from_organization_we_vote_id, to_organization_we_vote_id):
    status = ''
    success = False
    to_voter_id = 0
    voter_guide_entries_moved = 0
    voter_guide_entries_not_moved = 0

    if not positive_value_exists(from_voter_we_vote_id) or not positive_value_exists(to_voter_we_vote_id):
        status += "MOVE_VOTER_GUIDES-MISSING_EITHER_FROM_OR_TO_VOTER_WE_VOTE_ID "
        results = {
            'status': status,
            'success': success,
            'from_voter_we_vote_id': from_voter_we_vote_id,
            'to_voter_we_vote_id': to_voter_we_vote_id,
            'voter_guide_entries_moved': voter_guide_entries_moved,
            'voter_guide_entries_not_moved': voter_guide_entries_not_moved,
        }
        return results

    if from_voter_we_vote_id == to_voter_we_vote_id:
        status += "MOVE_VOTER_GUIDES-FROM_AND_TO_VOTER_WE_VOTE_IDS_IDENTICAL "
        results = {
            'status': status,
            'success': success,
            'from_voter_we_vote_id': from_voter_we_vote_id,
            'to_voter_we_vote_id': to_voter_we_vote_id,
            'voter_guide_entries_moved': voter_guide_entries_moved,
            'voter_guide_entries_not_moved': voter_guide_entries_not_moved,
        }
        return results

    if not positive_value_exists(from_organization_we_vote_id) or not positive_value_exists(to_organization_we_vote_id):
        status += "MOVE_VOTER_GUIDES-MISSING_EITHER_FROM_OR_TO_ORGANIZATION_WE_VOTE_ID "

    voter_guide_list_manager = VoterGuideListManager()
    for_editing = True

    from_voter_guide_results = voter_guide_list_manager.retrieve_all_voter_guides_by_voter_we_vote_id(
        from_voter_we_vote_id, for_editing)
    if from_voter_guide_results['voter_guide_list_found']:
        from_voter_guide_list = from_voter_guide_results['voter_guide_list']
    else:
        from_voter_guide_list = []

    from_voter_guide_list_count = len(from_voter_guide_list)

    if not positive_value_exists(from_voter_guide_list_count):
        status += "MOVE_VOTER_GUIDES-NO_FROM_VOTER_GUIDES_FOUND "
        results = {
            'status': status,
            'success': success,
            'from_voter_we_vote_id': from_voter_we_vote_id,
            'to_voter_we_vote_id': to_voter_we_vote_id,
            'voter_guide_entries_moved': voter_guide_entries_moved,
            'voter_guide_entries_not_moved': voter_guide_entries_not_moved,
        }
        return results

    to_voter_guide_results = voter_guide_list_manager.retrieve_all_voter_guides_by_voter_we_vote_id(
        to_voter_we_vote_id, for_editing)
    if to_voter_guide_results['voter_guide_list_found']:
        to_voter_guide_list = to_voter_guide_results['voter_guide_list']
    else:
        to_voter_guide_list = []

    voter_manager = VoterManager()
    for from_voter_guide in from_voter_guide_list:
        # See if the "to_voter" already has a matching entry
        to_voter_guide_found = False
        from_voter_guide_google_civic_election_id = from_voter_guide.google_civic_election_id
        # Cycle through all of the "to_voter" current_friend entries and if there isn't one, create it
        for to_voter_guide in to_voter_guide_list:
            to_voter_guide_google_civic_election_id = to_voter_guide.google_civic_election_id
            if to_voter_guide_google_civic_election_id == from_voter_guide_google_civic_election_id:
                to_voter_guide_found = True
                break

        if to_voter_guide_found:
            # We don't do anything with the from_voter_guide, and end up deleting it below
            pass
        else:
            # Change the voter and organization values to the new values
            if not positive_value_exists(to_voter_id):
                to_voter_id = voter_manager.fetch_local_id_from_we_vote_id(to_voter_we_vote_id)
            try:
                from_voter_guide.owner_voter_id = to_voter_id
                from_voter_guide.owner_voter_we_vote_id = to_voter_we_vote_id
                from_voter_guide.organization_we_vote_id = to_organization_we_vote_id
                from_voter_guide.save()
                voter_guide_entries_moved += 1
            except Exception as e:
                voter_guide_entries_not_moved += 1

    # Now remove the voter_guides where there were duplicates
    from_voter_guide_remaining_results = voter_guide_list_manager.retrieve_all_voter_guides_by_voter_we_vote_id(
        from_voter_we_vote_id, for_editing)
    if from_voter_guide_remaining_results['voter_guide_list_found']:
        from_voter_guide_list_remaining = to_voter_guide_results['voter_guide_list']
        for from_voter_guide in from_voter_guide_list_remaining:
            # Delete the remaining voter_guides
            try:
                # Leave this turned off until testing is finished
                # from_voter_guide.delete()
                pass
            except Exception as e:
                pass

    results = {
        'status': status,
        'success': success,
        'from_voter_we_vote_id': from_voter_we_vote_id,
        'to_voter_we_vote_id': to_voter_we_vote_id,
        'voter_guide_entries_moved': voter_guide_entries_moved,
        'voter_guide_entries_not_moved': voter_guide_entries_not_moved,
    }
    return results


def voter_guides_import_from_master_server(request, google_civic_election_id):
    """
    Get the json data, and either create new entries or update existing
    :return:
    """
    import_results, structured_json = process_request_from_master(
        request, "Loading Voter Guides from We Vote Master servers",
        VOTER_GUIDES_SYNC_URL, {
            "key":                      WE_VOTE_API_KEY,  # This comes from an environment variable
            "format":                   'json',
            "google_civic_election_id": str(google_civic_election_id),
        }
    )

    if import_results['success']:
        # results = filter_voter_guides_structured_json_for_local_duplicates(structured_json)
        # filtered_structured_json = results['structured_json']
        # duplicates_removed = results['duplicates_removed']
        filtered_structured_json = structured_json
        duplicates_removed = 0

        import_results = voter_guides_import_from_structured_json(filtered_structured_json)
        import_results['duplicates_removed'] = duplicates_removed

    return import_results


def filter_voter_guides_structured_json_for_local_duplicates(structured_json):
    """
    With this function, we remove voter_guides that seem to be duplicates, but have different we_vote_id's.
    :param structured_json:
    :return:
    """
    duplicates_removed = 0
    filtered_structured_json = []
    voter_guide_list_manager = VoterGuideListManager()
    for one_voter_guide in structured_json:
        we_vote_id = one_voter_guide['we_vote_id'] if 'we_vote_id' in one_voter_guide else ''
        google_civic_election_id = one_voter_guide['google_civic_election_id'] \
            if 'google_civic_election_id' in one_voter_guide else ''
        vote_smart_time_span = one_voter_guide['vote_smart_time_span'] \
            if 'vote_smart_time_span' in one_voter_guide else ''
        organization_we_vote_id = one_voter_guide['organization_we_vote_id'] \
            if 'organization_we_vote_id' in one_voter_guide else ''
        public_figure_we_vote_id = one_voter_guide['public_figure_we_vote_id'] \
            if 'public_figure_we_vote_id' in one_voter_guide else ''
        twitter_handle = one_voter_guide['twitter_handle'] if 'twitter_handle' in one_voter_guide else ''

        # Check to see if there is an entry that matches in all critical ways, minus the we_vote_id
        we_vote_id_from_master = we_vote_id

        results = voter_guide_list_manager.retrieve_possible_duplicate_voter_guides(
            google_civic_election_id, vote_smart_time_span,
            organization_we_vote_id, public_figure_we_vote_id,
            twitter_handle,
            we_vote_id_from_master)

        if results['voter_guide_list_found']:
            # There seems to be a duplicate already in this database using a different we_vote_id
            duplicates_removed += 1
        else:
            filtered_structured_json.append(one_voter_guide)

    voter_guides_results = {
        'success':              True,
        'status':               "FILTER_VOTER_GUIDES_FOR_DUPLICATES_PROCESS_COMPLETE",
        'duplicates_removed':   duplicates_removed,
        'structured_json':      filtered_structured_json,
    }
    return voter_guides_results


def voter_guides_import_from_structured_json(structured_json):
    """
    This pathway in requires a voter_guide_we_vote_id, and is not used when we import from Google Civic
    :param structured_json:
    :return:
    """
    voter_guide_manager = VoterGuideManager()
    organization_manager = OrganizationManager()
    organization_id = 0
    voter_guides_saved = 0
    voter_guides_updated = 0
    voter_guides_not_processed = 0
    for one_voter_guide in structured_json:
        voter_guide_we_vote_id = one_voter_guide['we_vote_id'] if 'we_vote_id' in one_voter_guide else ''
        google_civic_election_id = one_voter_guide['google_civic_election_id'] \
            if 'google_civic_election_id' in one_voter_guide else ''
        # This is recalculated, so technically not needed here
        election_day_text = one_voter_guide['election_day_text'] \
            if 'election_day_text' in one_voter_guide else ''
        vote_smart_time_span = one_voter_guide['vote_smart_time_span'] \
            if 'vote_smart_time_span' in one_voter_guide else ''
        organization_we_vote_id = one_voter_guide['organization_we_vote_id'] \
            if 'organization_we_vote_id' in one_voter_guide else ''
        public_figure_we_vote_id = one_voter_guide['public_figure_we_vote_id'] \
            if 'public_figure_we_vote_id' in one_voter_guide else ''
        state_code = one_voter_guide['state_code'] if 'state_code' in one_voter_guide else ''
        pledge_count = one_voter_guide['pledge_count'] if 'pledge_count' in one_voter_guide else ''
        pledge_goal = one_voter_guide['pledge_goal'] if 'pledge_goal' in one_voter_guide else ''
        we_vote_hosted_profile_image_url_large = one_voter_guide['we_vote_hosted_profile_image_url_large'] \
            if 'we_vote_hosted_profile_image_url_large' in one_voter_guide else ''
        we_vote_hosted_profile_image_url_medium = one_voter_guide['we_vote_hosted_profile_image_url_medium'] \
            if 'we_vote_hosted_profile_image_url_medium' in one_voter_guide else ''
        we_vote_hosted_profile_image_url_tiny = one_voter_guide['we_vote_hosted_profile_image_url_tiny'] \
            if 'we_vote_hosted_profile_image_url_tiny' in one_voter_guide else ''

        if positive_value_exists(voter_guide_we_vote_id) and \
                (positive_value_exists(organization_we_vote_id) or
                 positive_value_exists(public_figure_we_vote_id)) and \
                (positive_value_exists(google_civic_election_id) or
                 positive_value_exists(vote_smart_time_span)):
            # Make sure we have the organization (or public figure) in this database before we import the voter guide
            if positive_value_exists(organization_we_vote_id):
                results = organization_manager.retrieve_organization_from_we_vote_id(organization_we_vote_id)
                if results['organization_found']:
                    organization_id = results['organization_id']
                if positive_value_exists(organization_id):
                    proceed_to_update_or_create = True
                else:
                    proceed_to_update_or_create = False
            elif positive_value_exists(public_figure_we_vote_id):
                # TODO DALE Update this to work with public_figure
                public_figure_id = organization_manager.retrieve_organization_from_we_vote_id(public_figure_we_vote_id)
                if positive_value_exists(public_figure_id):
                    proceed_to_update_or_create = True
                else:
                    proceed_to_update_or_create = False
            else:
                proceed_to_update_or_create = False
        else:
            proceed_to_update_or_create = False

        if proceed_to_update_or_create:
            if positive_value_exists(organization_we_vote_id) and positive_value_exists(google_civic_election_id):
                results = voter_guide_manager.update_or_create_organization_voter_guide_by_election_id(
                    voter_guide_we_vote_id, organization_we_vote_id, google_civic_election_id, state_code, pledge_goal,
                    we_vote_hosted_profile_image_url_large, we_vote_hosted_profile_image_url_medium,
                    we_vote_hosted_profile_image_url_tiny
                )
            elif positive_value_exists(organization_we_vote_id) and positive_value_exists(vote_smart_time_span):
                results = voter_guide_manager.update_or_create_organization_voter_guide_by_time_span(
                    voter_guide_we_vote_id, organization_we_vote_id, vote_smart_time_span, pledge_goal,
                    we_vote_hosted_profile_image_url_large, we_vote_hosted_profile_image_url_medium,
                    we_vote_hosted_profile_image_url_tiny)
            elif positive_value_exists(public_figure_we_vote_id) and positive_value_exists(google_civic_election_id):
                results = voter_guide_manager.update_or_create_public_figure_voter_guide(
                    voter_guide_we_vote_id, google_civic_election_id, public_figure_we_vote_id, pledge_goal,
                    we_vote_hosted_profile_image_url_large, we_vote_hosted_profile_image_url_medium,
                    we_vote_hosted_profile_image_url_tiny)
            else:
                results = {
                    'success': False,
                    'status': 'Required value missing, cannot update or create (1)'
                }
        else:
            voter_guides_not_processed += 1
            results = {
                'success': False,
                'status': 'Required value missing, cannot update or create (2)'
            }

        if results['success']:
            if results['new_voter_guide_created']:
                voter_guides_saved += 1
            else:
                voter_guides_updated += 1
        else:
            voter_guides_not_processed += 1
    voter_guides_results = {
        'success':          True,
        'status':           "VOTER_GUIDES_IMPORT_PROCESS_COMPLETE",
        'saved':            voter_guides_saved,
        'updated':          voter_guides_updated,
        'not_processed':    voter_guides_not_processed,
    }
    return voter_guides_results


def voter_guide_possibility_retrieve_for_api(voter_device_id, voter_guide_possibility_url):
    results = is_voter_device_id_valid(voter_device_id)
    voter_guide_possibility_url = voter_guide_possibility_url  # TODO Use scrapy here
    if not results['success']:
        return HttpResponse(json.dumps(results['json_data']), content_type='application/json')

    voter_id = fetch_voter_id_from_voter_device_link(voter_device_id)
    if not positive_value_exists(voter_id):
        json_data = {
            'status': "VOTER_NOT_FOUND_FROM_VOTER_DEVICE_ID",
            'success': False,
            'voter_device_id': voter_device_id,
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    # TODO We will need the voter_id here so we can control volunteer actions

    voter_guide_possibility_manager = VoterGuidePossibilityManager()
    results = voter_guide_possibility_manager.retrieve_voter_guide_possibility_from_url(voter_guide_possibility_url)

    json_data = {
        'voter_device_id':              voter_device_id,
        'voter_guide_possibility_url':  results['voter_guide_possibility_url'],
        'voter_guide_possibility_id':   results['voter_guide_possibility_id'],
        'organization_we_vote_id':      results['organization_we_vote_id'],
        'public_figure_we_vote_id':     results['public_figure_we_vote_id'],
        'owner_we_vote_id':             results['owner_we_vote_id'],
        'status':                       results['status'],
        'success':                      results['success'],
    }
    return HttpResponse(json.dumps(json_data), content_type='application/json')


def voter_guide_possibility_save_for_api(voter_device_id, voter_guide_possibility_url):
    results = is_voter_device_id_valid(voter_device_id)
    if not results['success']:
        return HttpResponse(json.dumps(results['json_data']), content_type='application/json')

    if not voter_guide_possibility_url:
        json_data = {
                'status': "MISSING_POST_VARIABLE-URL",
                'success': False,
                'voter_device_id': voter_device_id,
            }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    voter_id = fetch_voter_id_from_voter_device_link(voter_device_id)
    if not positive_value_exists(voter_id):
        json_data = {
            'status': "VOTER_NOT_FOUND_FROM_DEVICE_ID",
            'success': False,
            'voter_device_id': voter_device_id,
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    # At this point, we have a valid voter

    voter_guide_possibility_manager = VoterGuidePossibilityManager()

    # We wrap get_or_create because we want to centralize error handling
    results = voter_guide_possibility_manager.update_or_create_voter_guide_possibility(
        voter_guide_possibility_url.strip())
    if results['success']:
        json_data = {
                'status': "VOTER_GUIDE_POSSIBILITY_SAVED",
                'success': True,
                'voter_device_id': voter_device_id,
                'voter_guide_possibility_url': voter_guide_possibility_url,
            }

    # elif results['status'] == 'MULTIPLE_MATCHING_ADDRESSES_FOUND':
        # delete all currently matching addresses and save again?
    else:
        json_data = {
                'status': results['status'],
                'success': False,
                'voter_device_id': voter_device_id,
            }
    return HttpResponse(json.dumps(json_data), content_type='application/json')


def voter_guides_to_follow_retrieve_for_api(voter_device_id,  # voterGuidesToFollowRetrieve
                                            kind_of_ballot_item='', ballot_item_we_vote_id='',
                                            google_civic_election_id=0, search_string='',
                                            start_retrieve_at_this_number=0,
                                            maximum_number_to_retrieve=0,
                                            filter_voter_guides_by_issue=False,
                                            add_voter_guides_not_from_election=False):
    voter_we_vote_id = ""
    start_retrieve_at_this_number = convert_to_int(start_retrieve_at_this_number)
    number_retrieved = 0
    filter_voter_guides_by_issue = positive_value_exists(filter_voter_guides_by_issue)
    add_voter_guides_not_from_election = positive_value_exists(add_voter_guides_not_from_election)
    status = ""
    # Get voter_id from the voter_device_id so we can figure out which voter_guides to offer
    results = is_voter_device_id_valid(voter_device_id)
    if not results['success']:
        json_data = {
            'status': 'ERROR_GUIDES_TO_FOLLOW_NO_VOTER_DEVICE_ID',
            'success': False,
            'voter_device_id': voter_device_id,
            'voter_guides': [],
            'start_retrieve_at_this_number': start_retrieve_at_this_number,
            'number_retrieved': number_retrieved,
            'maximum_number_to_retrieve': maximum_number_to_retrieve,
            'google_civic_election_id': google_civic_election_id,
            'search_string': search_string,
            'ballot_item_we_vote_id': ballot_item_we_vote_id,
        }
        results = {
            'success': False,
            'google_civic_election_id': 0,  # Force the reset of google_civic_election_id cookie
            'ballot_item_we_vote_id': ballot_item_we_vote_id,
            'json_data': json_data,
        }
        return results

    voter_id = fetch_voter_id_from_voter_device_link(voter_device_id)
    if not positive_value_exists(voter_id):
        json_data = {
            'status': "ERROR_GUIDES_TO_FOLLOW_VOTER_NOT_FOUND_FROM_VOTER_DEVICE_ID",
            'success': False,
            'voter_device_id': voter_device_id,
            'voter_guides': [],
            'start_retrieve_at_this_number': start_retrieve_at_this_number,
            'number_retrieved': number_retrieved,
            'maximum_number_to_retrieve': maximum_number_to_retrieve,
            'google_civic_election_id': google_civic_election_id,
            'search_string': search_string,
            'ballot_item_we_vote_id': ballot_item_we_vote_id,
        }
        results = {
            'success': False,
            'google_civic_election_id': 0,  # Force the reset of google_civic_election_id cookie
            'ballot_item_we_vote_id': ballot_item_we_vote_id,
            'json_data': json_data,
        }
        return results

    # If filter_voter_guides_by_issue is set then fetch organization_we_vote_ids related to the
    # issues that the voter follows
    organization_we_vote_id_list_for_voter_issues = []
    if filter_voter_guides_by_issue:
        voter_we_vote_id = fetch_voter_we_vote_id_from_voter_device_link(voter_device_id)
        if not positive_value_exists(voter_we_vote_id):
            json_data = {
                'status': "ERROR_GUIDES_TO_FOLLOW_VOTER_NOT_FOUND_FROM_VOTER_DEVICE_ID VOTER_WE_VOTE_ID_NOT_FOUND",
                'success': False,
                'voter_device_id': voter_device_id,
                'voter_guides': [],
                'start_retrieve_at_this_number': start_retrieve_at_this_number,
                'number_retrieved': number_retrieved,
                'maximum_number_to_retrieve': maximum_number_to_retrieve,
                'google_civic_election_id': google_civic_election_id,
                'search_string': search_string,
            }
            results = {
                'success': False,
                'google_civic_election_id': 0,  # Force the reset of google_civic_election_id cookie
                'json_data': json_data,
            }
            return results
        else:
            follow_issue_list_manager = FollowIssueList()
            following_status = FOLLOWING
            issue_list_for_voter = follow_issue_list_manager. \
                retrieve_follow_issue_list_by_voter_we_vote_id(voter_we_vote_id, following_status)
            issue_list_for_voter = list(issue_list_for_voter)
            issue_we_vote_id_list_for_voter = []
            for issue in issue_list_for_voter:
                issue_we_vote_id_list_for_voter.append(issue.issue_we_vote_id)

            link_issue_list = OrganizationLinkToIssueList()
            organization_we_vote_id_list_result = link_issue_list. \
                retrieve_organization_we_vote_id_list_from_issue_we_vote_id_list(issue_we_vote_id_list_for_voter)
            organization_we_vote_id_list_for_voter_issues = \
                organization_we_vote_id_list_result['organization_we_vote_id_list']

    voter_guide_list = []
    voter_guides = []
    try:
        if positive_value_exists(kind_of_ballot_item) and positive_value_exists(ballot_item_we_vote_id):
            results = retrieve_voter_guides_to_follow_by_ballot_item(voter_id,
                                                                     kind_of_ballot_item, ballot_item_we_vote_id,
                                                                     search_string, filter_voter_guides_by_issue,
                                                                     organization_we_vote_id_list_for_voter_issues)
            success = results['success']
            status += results['status']
            voter_guide_list = results['voter_guide_list']
        elif positive_value_exists(google_civic_election_id):
            # This retrieve also does the reordering
            results = retrieve_voter_guides_to_follow_by_election_for_api(voter_id, google_civic_election_id,
                                                                          search_string,
                                                                          filter_voter_guides_by_issue,
                                                                          organization_we_vote_id_list_for_voter_issues,
                                                                          start_retrieve_at_this_number,
                                                                          maximum_number_to_retrieve,
                                                                          'twitter_followers_count', 'desc')
            success = results['success']
            voter_guide_list = results['voter_guide_list']
            status = results['status'] + ", len(voter_guide_list): " + str(len(voter_guide_list)) + " "
            if add_voter_guides_not_from_election:
                status += "ADDING_VOTER_GUIDES_NOT_FROM_ELECTION "
                non_election_results = retrieve_voter_guides_to_follow_generic_for_api(
                    voter_id, search_string,
                    filter_voter_guides_by_issue,
                    organization_we_vote_id_list_for_voter_issues,
                    maximum_number_to_retrieve,
                    'twitter_followers_count', 'desc')
                if non_election_results['success']:
                    status += non_election_results['status']
                    non_election_voter_guide_list = non_election_results['voter_guide_list']
                    voter_guide_list = voter_guide_list + non_election_voter_guide_list
        else:
            results = retrieve_voter_guides_to_follow_generic_for_api(voter_id, search_string,
                                                                      filter_voter_guides_by_issue,
                                                                      organization_we_vote_id_list_for_voter_issues,
                                                                      maximum_number_to_retrieve,
                                                                      'twitter_followers_count', 'desc')
            success = results['success']
            status += results['status']
            voter_guide_list = results['voter_guide_list']

    except Exception as e:
        status += 'FAILED voter_guides_to_follow_retrieve_for_api, retrieve_voter_guides_for_election ' \
                 '{error} [type: {error_type}]'.format(error=e, error_type=type(e))
        success = False

    if success:
        voter_manager = VoterManager()
        results = voter_manager.retrieve_voter_by_id(voter_id)
        linked_organization_we_vote_id = ""
        if results['voter_found']:
            voter = results['voter']
            voter_we_vote_id = voter.we_vote_id
            linked_organization_we_vote_id = voter.linked_organization_we_vote_id

        number_added_to_list = 0
        position_manager = PositionManager()
        position = PositionEntered()
        pledge_to_vote_manager = PledgeToVoteManager()
        for voter_guide in voter_guide_list:
            if positive_value_exists(voter_guide.organization_we_vote_id) \
                    and positive_value_exists(linked_organization_we_vote_id) \
                    and linked_organization_we_vote_id == voter_guide.organization_we_vote_id:
                # Do not return your own voter guide to follow
                continue

            if hasattr(voter_guide, 'ballot_item_we_vote_ids_this_org_supports'):
                ballot_item_we_vote_ids_this_org_supports = voter_guide.ballot_item_we_vote_ids_this_org_supports
            else:
                ballot_item_we_vote_ids_this_org_supports = []

            if hasattr(voter_guide, 'ballot_item_we_vote_ids_this_org_info_only'):
                ballot_item_we_vote_ids_this_org_info_only = voter_guide.ballot_item_we_vote_ids_this_org_info_only
            else:
                ballot_item_we_vote_ids_this_org_info_only = []

            if hasattr(voter_guide, 'ballot_item_we_vote_ids_this_org_opposes'):
                ballot_item_we_vote_ids_this_org_opposes = voter_guide.ballot_item_we_vote_ids_this_org_opposes
            else:
                ballot_item_we_vote_ids_this_org_opposes = []

            organization_link_to_issue_list = OrganizationLinkToIssueList()
            issue_we_vote_ids_linked = \
                organization_link_to_issue_list.fetch_issue_we_vote_id_list_by_organization_we_vote_id(
                    voter_guide.organization_we_vote_id)

            pledge_to_vote_we_vote_id = ""
            pledge_results = pledge_to_vote_manager.retrieve_pledge_to_vote(
                pledge_to_vote_we_vote_id, voter_we_vote_id, voter_guide.we_vote_id)
            if pledge_results['pledge_found']:
                voter_has_pledged = pledge_results['voter_has_pledged']
            else:
                voter_has_pledged = False
            position_found = False
            one_voter_guide = {
                'we_vote_id':                   voter_guide.we_vote_id,
                'google_civic_election_id':     voter_guide.google_civic_election_id,
                'time_span':                    voter_guide.vote_smart_time_span,
                'voter_guide_display_name':     voter_guide.voter_guide_display_name(),
                'voter_guide_image_url_large':  voter_guide.we_vote_hosted_profile_image_url_large
                if positive_value_exists(voter_guide.we_vote_hosted_profile_image_url_large)
                else voter_guide.voter_guide_image_url(),
                'voter_guide_image_url_medium': voter_guide.we_vote_hosted_profile_image_url_medium,
                'voter_guide_image_url_tiny':   voter_guide.we_vote_hosted_profile_image_url_tiny,
                'voter_guide_owner_type':       voter_guide.voter_guide_owner_type,
                'organization_we_vote_id':      voter_guide.organization_we_vote_id,
                'public_figure_we_vote_id':     voter_guide.public_figure_we_vote_id,
                'twitter_description':          voter_guide.twitter_description,
                'twitter_followers_count':      voter_guide.twitter_followers_count,
                'twitter_handle':               voter_guide.twitter_handle,
                'owner_voter_id':               voter_guide.owner_voter_id,
                'ballot_item_we_vote_ids_this_org_supports':    ballot_item_we_vote_ids_this_org_supports,
                'ballot_item_we_vote_ids_this_org_info_only':   ballot_item_we_vote_ids_this_org_info_only,
                'ballot_item_we_vote_ids_this_org_opposes':     ballot_item_we_vote_ids_this_org_opposes,
                'issue_we_vote_ids_linked':     issue_we_vote_ids_linked,
                'pledge_goal':                  voter_guide.pledge_goal,
                'pledge_count':                 voter_guide.pledge_count,
                'voter_has_pledged':            voter_has_pledged,
                'last_updated':                 voter_guide.last_updated.strftime('%Y-%m-%d %H:%M'),
            }
            if positive_value_exists(ballot_item_we_vote_id):
                if kind_of_ballot_item == CANDIDATE:
                    organization_manager = OrganizationManager()
                    organization_id = organization_manager.fetch_organization_id(
                        voter_guide.organization_we_vote_id)
                    results = position_manager.retrieve_organization_candidate_campaign_position_with_we_vote_id(
                        organization_id, ballot_item_we_vote_id)
                    if results['position_found']:
                        position = results['position']
                        position_found = True
                elif kind_of_ballot_item == MEASURE:
                    organization_manager = OrganizationManager()
                    organization_id = organization_manager.fetch_organization_id(
                        voter_guide.organization_we_vote_id)
                    results = position_manager.retrieve_organization_contest_measure_position_with_we_vote_id(
                        organization_id, ballot_item_we_vote_id)
                    if results['position_found']:
                        position = results['position']
                        position_found = True

                # Since a ballot_item_we_vote_id came in, we only want to return a voter guide if there is a
                #  support, oppose, or a comment
                if position_found:
                    if position.is_support_or_positive_rating() or position.is_oppose_or_negative_rating() or \
                            position.statement_text or is_link_to_video(position.more_info_url):
                        # We can proceed
                        pass
                    else:
                        # We shouldn't return a voter_guide in this case without support/oppose/or a comment
                        continue

                if position_found:
                    one_voter_guide['is_support'] = position.is_support()
                    one_voter_guide['is_positive_rating'] = position.is_positive_rating()
                    one_voter_guide['is_support_or_positive_rating'] = position.is_support_or_positive_rating()
                    one_voter_guide['is_oppose'] = position.is_oppose()
                    one_voter_guide['is_negative_rating'] = position.is_negative_rating()
                    one_voter_guide['is_oppose_or_negative_rating'] = position.is_oppose_or_negative_rating()
                    one_voter_guide['is_information_only'] = position.is_information_only()
                    one_voter_guide['ballot_item_display_name'] = position.ballot_item_display_name
                    one_voter_guide['speaker_display_name'] = position.speaker_display_name
                    one_voter_guide['statement_text'] = position.statement_text
                    one_voter_guide['more_info_url'] = position.more_info_url
                    one_voter_guide['has_video'] = is_link_to_video(position.more_info_url)
                    one_voter_guide['vote_smart_rating'] = position.vote_smart_rating
                    one_voter_guide['vote_smart_time_span'] = position.vote_smart_time_span

            voter_guides.append(one_voter_guide.copy())
            if positive_value_exists(maximum_number_to_retrieve):
                number_added_to_list += 1
                if number_added_to_list >= maximum_number_to_retrieve:
                    break

        number_retrieved = len(voter_guides)
        if positive_value_exists(number_retrieved):
            json_data = {
                'status': status + ' VOTER_GUIDES_TO_FOLLOW_FOR_API_RETRIEVED',
                'success': True,
                'voter_device_id': voter_device_id,
                'voter_guides': voter_guides,
                'google_civic_election_id': google_civic_election_id,
                'search_string': search_string,
                'ballot_item_we_vote_id': ballot_item_we_vote_id,
                'start_retrieve_at_this_number': start_retrieve_at_this_number,
                'number_retrieved': number_retrieved,
                'maximum_number_to_retrieve': maximum_number_to_retrieve,
                'filter_voter_guides_by_issue': filter_voter_guides_by_issue
            }
        else:
            json_data = {
                'status': status + ' NO_VOTER_GUIDES_FOUND',
                'success': True,
                'voter_device_id': voter_device_id,
                'voter_guides': voter_guides,
                'google_civic_election_id': google_civic_election_id,
                'search_string': search_string,
                'ballot_item_we_vote_id': ballot_item_we_vote_id,
                'start_retrieve_at_this_number': start_retrieve_at_this_number,
                'number_retrieved': number_retrieved,
                'maximum_number_to_retrieve': maximum_number_to_retrieve,
                'filter_voter_guides_by_issue': filter_voter_guides_by_issue
            }

        results = {
            'success': success,
            'google_civic_election_id': google_civic_election_id,
            'ballot_item_we_vote_id': ballot_item_we_vote_id,
            'json_data': json_data,
        }
        return results
    else:
        json_data = {
            'status': status,
            'success': False,
            'voter_device_id': voter_device_id,
            'voter_guides': [],
            'start_retrieve_at_this_number': start_retrieve_at_this_number,
            'number_retrieved': number_retrieved,
            'maximum_number_to_retrieve': maximum_number_to_retrieve,
            'google_civic_election_id': google_civic_election_id,
            'search_string': search_string,
            'ballot_item_we_vote_id': ballot_item_we_vote_id,
        }

        results = {
            'success': False,
            'google_civic_election_id': 0,  # Force the reset of google_civic_election_id cookie
            'ballot_item_we_vote_id': ballot_item_we_vote_id,
            'json_data': json_data,
        }
        return results


def retrieve_voter_guides_to_follow_by_ballot_item(voter_id, kind_of_ballot_item, ballot_item_we_vote_id,
                                                   search_string, filter_voter_guides_by_issue=None,
                                                   organization_we_vote_id_list_for_voter_issues=None):
    if filter_voter_guides_by_issue is None:
        filter_voter_guides_by_issue = False
    voter_guide_list_found = False
    retrieve_public_positions = True  # The alternate is positions for friends-only. Since this method returns positions
    # to follow, we never need to return friend's positions here

    position_list_manager = PositionListManager()
    if (kind_of_ballot_item == CANDIDATE) and positive_value_exists(ballot_item_we_vote_id):
        candidate_id = 0
        all_positions_list = position_list_manager.retrieve_all_positions_for_candidate_campaign(
            retrieve_public_positions, candidate_id, ballot_item_we_vote_id, ANY_STANCE)
    elif (kind_of_ballot_item == MEASURE) and positive_value_exists(ballot_item_we_vote_id):
        measure_id = 0
        all_positions_list = position_list_manager.retrieve_all_positions_for_contest_measure(
            retrieve_public_positions, measure_id, ballot_item_we_vote_id, ANY_STANCE)
    elif (kind_of_ballot_item == OFFICE) and positive_value_exists(ballot_item_we_vote_id):
        office_id = 0
        all_positions_list = position_list_manager.retrieve_all_positions_for_contest_office(
                office_id, ballot_item_we_vote_id, ANY_STANCE)
    else:
        voter_guide_list = []
        results = {
            'success':                      False,
            'status':                       "VOTER_GUIDES_BALLOT_RELATED_VARIABLES_MISSING",
            'search_string':                search_string,
            'voter_guide_list_found':       False,
            'voter_guide_list':             voter_guide_list,
        }
        return results

    if filter_voter_guides_by_issue and organization_we_vote_id_list_for_voter_issues is not None:
        all_positions_list = position_list_manager.remove_positions_unrelated_to_issues(
            all_positions_list, organization_we_vote_id_list_for_voter_issues)

    follow_organization_list_manager = FollowOrganizationList()
    organizations_followed_by_voter = \
        follow_organization_list_manager.retrieve_follow_organization_by_voter_id_simple_id_array(voter_id)

    positions_list = position_list_manager.calculate_positions_not_followed_by_voter(
        all_positions_list, organizations_followed_by_voter)

    voter_guide_list = []
    # Cycle through the positions held by groups that you don't currently follow
    voter_guide_manager = VoterGuideManager()
    for one_position in positions_list:
        if positive_value_exists(one_position.organization_we_vote_id):
            if one_position.google_civic_election_id:
                results = voter_guide_manager.retrieve_voter_guide(
                    voter_guide_id=0,
                    google_civic_election_id=one_position.google_civic_election_id,
                    vote_smart_time_span=None,
                    organization_we_vote_id=one_position.organization_we_vote_id)
            else:
                # vote_smart_time_span
                results = voter_guide_manager.retrieve_voter_guide(
                    voter_guide_id=0,
                    google_civic_election_id=0,
                    vote_smart_time_span=one_position.vote_smart_time_span,
                    organization_we_vote_id=one_position.organization_we_vote_id)

        elif positive_value_exists(one_position.public_figure_we_vote_id):
            results['voter_guide_found'] = False
        elif positive_value_exists(one_position.voter_we_vote_id):
            results['voter_guide_found'] = False
        else:
            results['voter_guide_found'] = False

        if results['voter_guide_found']:
            one_voter_guide = results['voter_guide']

            # Augment the voter guide with a list of ballot_item we_vote_id's that this org supports
            stance_we_are_looking_for = SUPPORT
            organization_id = 0
            ballot_item_support_results = retrieve_ballot_item_we_vote_ids_for_organizations_to_follow(
                voter_id, organization_id, one_voter_guide.organization_we_vote_id, stance_we_are_looking_for,
                one_position.google_civic_election_id)

            if ballot_item_support_results['count']:
                ballot_item_we_vote_ids_this_org_supports = ballot_item_support_results['ballot_item_we_vote_ids_list']
            else:
                ballot_item_we_vote_ids_this_org_supports = []

            one_voter_guide.ballot_item_we_vote_ids_this_org_supports = \
                ballot_item_we_vote_ids_this_org_supports

            # Augment the voter guide with a list of ballot_item we_vote_id's that this org has info about
            stance_we_are_looking_for = INFORMATION_ONLY
            organization_id = 0
            ballot_item_info_only_results = retrieve_ballot_item_we_vote_ids_for_organizations_to_follow(
                voter_id, organization_id, one_voter_guide.organization_we_vote_id, stance_we_are_looking_for,
                one_position.google_civic_election_id)

            if ballot_item_info_only_results['count']:
                ballot_item_we_vote_ids_this_org_info_only = \
                    ballot_item_info_only_results['ballot_item_we_vote_ids_list']
            else:
                ballot_item_we_vote_ids_this_org_info_only = []

            one_voter_guide.ballot_item_we_vote_ids_this_org_info_only = \
                ballot_item_we_vote_ids_this_org_info_only

            # Augment the voter guide with a list of ballot_item we_vote_id's that this org opposes
            stance_we_are_looking_for = OPPOSE
            organization_id = 0
            ballot_item_oppose_results = retrieve_ballot_item_we_vote_ids_for_organizations_to_follow(
                voter_id, organization_id, one_voter_guide.organization_we_vote_id, stance_we_are_looking_for,
                one_position.google_civic_election_id)

            if ballot_item_oppose_results['count']:
                ballot_item_we_vote_ids_this_org_opposes = ballot_item_oppose_results['ballot_item_we_vote_ids_list']
            else:
                ballot_item_we_vote_ids_this_org_opposes = []

            one_voter_guide.ballot_item_we_vote_ids_this_org_opposes = \
                ballot_item_we_vote_ids_this_org_opposes

            # If we passed in search_string, make sure they are in this entry.
            # If they aren't, don't return voter guide
            if positive_value_exists(search_string):
                search_string = str(search_string)  # Make sure search_string is a string
                twitter_handle = str(one_voter_guide.twitter_handle)
                display_name = str(one_voter_guide.display_name)

                if search_string.lower() in twitter_handle.lower() or search_string.lower() in display_name.lower():
                    voter_guide_list.append(one_voter_guide)
            else:
                voter_guide_list.append(one_voter_guide)

    status = 'SUCCESSFUL_RETRIEVE_OF_VOTER_GUIDES_BY_BALLOT_ITEM'
    success = True

    if len(voter_guide_list):
        voter_guide_list_found = True

    results = {
        'success':                      success,
        'status':                       status,
        'search_string':                search_string,
        'voter_guide_list_found':       voter_guide_list_found,
        'voter_guide_list':             voter_guide_list,
    }
    return results


def retrieve_voter_guides_to_follow_by_election_for_api(voter_id, google_civic_election_id, search_string,
                                                        filter_voter_guides_by_issue=False,
                                                        organization_we_vote_id_list_for_voter_issues=None,
                                                        start_retrieve_at_this_number=0,
                                                        maximum_number_to_retrieve=0, sort_by='', sort_order=''):
    filter_voter_guides_by_issue = positive_value_exists(filter_voter_guides_by_issue)

    voter_guide_list_found = False
    status = ""
    status += "voter_id: " + str(voter_id) + " "

    # Start with orgs followed and ignored by this voter
    follow_organization_list_manager = FollowOrganizationList()
    organizations_followed_by_voter = \
        follow_organization_list_manager.retrieve_follow_organization_by_voter_id_simple_id_array(voter_id)
    organizations_ignored_by_voter = \
        follow_organization_list_manager.retrieve_ignore_organization_by_voter_id_simple_id_array(voter_id)

    position_list_manager = PositionListManager()
    if positive_value_exists(google_civic_election_id):
        # This method finds all ballot_items in this election, and then retrieves *all* positions by any org or person
        # about each ballot_item. This will pick up We Vote positions or Vote Smart ratings, regardless of what time
        # period they were entered for.
        public_only = True  # Do not return positions that are from friends only since we only want public positions
        all_positions_list_for_election = position_list_manager.retrieve_all_positions_for_election(
            google_civic_election_id, ANY_STANCE, public_only)
    else:
        voter_guide_list = []
        results = {
            'success':                      False,
            'status':                       "VOTER_GUIDES_BALLOT_RELATED_VARIABLES_MISSING",
            'voter_guide_list_found':       False,
            'voter_guide_list':             voter_guide_list,
        }
        return results

    if filter_voter_guides_by_issue and organization_we_vote_id_list_for_voter_issues is not None:
        all_positions_list_for_election = position_list_manager.remove_positions_unrelated_to_issues(
            all_positions_list_for_election, organization_we_vote_id_list_for_voter_issues)

    positions_list_minus_ignored = position_list_manager.remove_positions_ignored_by_voter(
        all_positions_list_for_election, organizations_ignored_by_voter)

    positions_list_minus_ignored_and_followed = position_list_manager.calculate_positions_not_followed_by_voter(
        positions_list_minus_ignored, organizations_followed_by_voter)

    if not len(positions_list_minus_ignored_and_followed):
        # If no positions are found, exit
        voter_guide_list = []
        results = {
            'success':                      True,
            'status':                       "NO_VOTER_GUIDES_FOUND_FOR_THIS_ELECTION",
            'voter_guide_list_found':       False,
            'voter_guide_list':             voter_guide_list,
        }
        return results

    # We want to retrieve an ordered list of organization_we_vote_id's (not followed or ignored) that have a position
    # in this election. For speed we only retrieve full voter_guide data for the limited list that we need
    voter_guide_list_manager = VoterGuideListManager()
    # This is a list of orgs that the voter isn't following or ignoring
    org_list_found_by_google_civic_election_id = []
    for one_position in positions_list_minus_ignored_and_followed:
        if positive_value_exists(one_position.organization_we_vote_id) and \
                positive_value_exists(one_position.google_civic_election_id):
            # Make sure we haven't already recorded that we want to retrieve the voter_guide for this org
            if one_position.organization_we_vote_id in org_list_found_by_google_civic_election_id:
                continue
            org_list_found_by_google_civic_election_id.append(one_position.organization_we_vote_id)

    # status += " len(org_list_found_by_google_civic_election_id): " + \
    #           str(len(org_list_found_by_google_civic_election_id))

    # First, retrieve the voter_guides stored by org and google_civic_election_id
    if positive_value_exists(len(org_list_found_by_google_civic_election_id)):
        voter_guide_results = voter_guide_list_manager.retrieve_voter_guides_to_follow_by_election(
            google_civic_election_id, org_list_found_by_google_civic_election_id, search_string,
            start_retrieve_at_this_number,
            maximum_number_to_retrieve, sort_by, sort_order)

        status += " " + voter_guide_results['status'] + " "

        if voter_guide_results['voter_guide_list_found']:
            voter_guide_list_from_election_id = voter_guide_results['voter_guide_list']
            list_from_election_id_found = True
        else:
            voter_guide_list_from_election_id = []
            list_from_election_id_found = False
    else:
        voter_guide_list_from_election_id = []
        list_from_election_id_found = False

    # Second, retrieve the voter_guides stored by org & vote_smart_time_span
    # All positions were found above with position_list_manager.retrieve_all_positions_for_election
    # We give precedence to full voter guides from above, where we have an actual position of an org (as opposed to
    # Vote Smart ratings)
    maximum_number_of_guides_to_retrieve_by_time_span = \
        maximum_number_to_retrieve - len(voter_guide_list_from_election_id)
    if positive_value_exists(maximum_number_of_guides_to_retrieve_by_time_span):
        org_list_found_by_time_span = []
        orgs_we_need_found_by_position_and_time_span_list_of_dicts = []
        for one_position in positions_list_minus_ignored_and_followed:
            # If this was a position found that was based on vote_smart_time_span...
            #  (That is, ignore the positions already retrieved based on google_civic_election_id)
            if positive_value_exists(one_position.organization_we_vote_id) and \
                    positive_value_exists(one_position.vote_smart_time_span):
                # This shouldn't be possible, but we have it here for safety
                org_found_by_election_id_above = one_position.organization_we_vote_id in \
                    org_list_found_by_google_civic_election_id
                # If we already recorded that we want to look for this org under a different time span...
                org_found_by_different_time_span = one_position.organization_we_vote_id in \
                    org_list_found_by_time_span
                # Don't record that we want to look for a voter guide by this org we_vote_id or time span
                if org_found_by_election_id_above or org_found_by_different_time_span:
                    continue

                org_list_found_by_time_span.append(one_position.organization_we_vote_id)
                one_position_dict = {'organization_we_vote_id': one_position.organization_we_vote_id,
                                     'vote_smart_time_span': one_position.vote_smart_time_span}
                orgs_we_need_found_by_position_and_time_span_list_of_dicts.append(one_position_dict)

        voter_guide_time_span_results = voter_guide_list_manager.retrieve_voter_guides_to_follow_by_time_span(
            orgs_we_need_found_by_position_and_time_span_list_of_dicts,
            search_string,
            maximum_number_of_guides_to_retrieve_by_time_span, sort_by, sort_order)

        if voter_guide_time_span_results['voter_guide_list_found']:
            voter_guide_list_from_time_span = voter_guide_time_span_results['voter_guide_list']
            list_from_time_span_found = True
        else:
            voter_guide_list_from_time_span = []
            list_from_time_span_found = False
    else:
        voter_guide_list_from_time_span = []
        list_from_time_span_found = False

    # Merge these two lists
    if list_from_election_id_found and list_from_time_span_found:
        voter_guide_list = list(chain(voter_guide_list_from_election_id, voter_guide_list_from_time_span))
    elif list_from_election_id_found:
        voter_guide_list = list(voter_guide_list_from_election_id)
    elif list_from_time_span_found:
        voter_guide_list = list(voter_guide_list_from_time_span)
    else:
        voter_guide_list = []
    # IFF we wanted to sort here:
    # voter_guide_list = sorted(
    #     chain(voter_guide_list_from_election_id, voter_guide_list_from_time_span),
    #     key=attrgetter(sort_by))
    # But we don't, we just want to combine them with existing order

    status += 'SUCCESSFUL_RETRIEVE_OF_VOTER_GUIDES_BY_ELECTION '
    success = True

    if len(voter_guide_list):
        voter_guide_list_found = True
        updated_voter_guide_list = []
        for one_voter_guide in voter_guide_list:
            # Augment the voter guide with a list of ballot_item we_vote_id's that this org supports
            stance_we_are_looking_for = SUPPORT
            organization_id = 0
            ballot_item_support_results = retrieve_ballot_item_we_vote_ids_for_organizations_to_follow(
                voter_id, organization_id, one_voter_guide.organization_we_vote_id, stance_we_are_looking_for,
                google_civic_election_id)

            if ballot_item_support_results['count']:
                ballot_item_we_vote_ids_this_org_supports = ballot_item_support_results['ballot_item_we_vote_ids_list']
            else:
                ballot_item_we_vote_ids_this_org_supports = []

            one_voter_guide.ballot_item_we_vote_ids_this_org_supports = \
                ballot_item_we_vote_ids_this_org_supports

            # Augment the voter guide with a list of ballot_item we_vote_id's that this org has info about
            stance_we_are_looking_for = INFORMATION_ONLY
            organization_id = 0
            ballot_item_info_only_results = retrieve_ballot_item_we_vote_ids_for_organizations_to_follow(
                voter_id, organization_id, one_voter_guide.organization_we_vote_id, stance_we_are_looking_for,
                google_civic_election_id)

            if ballot_item_info_only_results['count']:
                ballot_item_we_vote_ids_this_org_info_only = \
                    ballot_item_info_only_results['ballot_item_we_vote_ids_list']
            else:
                ballot_item_we_vote_ids_this_org_info_only = []

            one_voter_guide.ballot_item_we_vote_ids_this_org_info_only = \
                ballot_item_we_vote_ids_this_org_info_only

            # Augment the voter guide with a list of ballot_item we_vote_id's that this org opposes
            stance_we_are_looking_for = OPPOSE
            organization_id = 0
            ballot_item_oppose_results = retrieve_ballot_item_we_vote_ids_for_organizations_to_follow(
                voter_id, organization_id, one_voter_guide.organization_we_vote_id, stance_we_are_looking_for,
                google_civic_election_id)

            if ballot_item_oppose_results['count']:
                ballot_item_we_vote_ids_this_org_opposes = ballot_item_oppose_results['ballot_item_we_vote_ids_list']
            else:
                ballot_item_we_vote_ids_this_org_opposes = []

            one_voter_guide.ballot_item_we_vote_ids_this_org_opposes = \
                ballot_item_we_vote_ids_this_org_opposes

            updated_voter_guide_list.append(one_voter_guide)
        voter_guide_list = updated_voter_guide_list

    results = {
        'success':                      success,
        'status':                       status,
        'voter_guide_list_found':       voter_guide_list_found,
        'voter_guide_list':             voter_guide_list,
    }
    return results


def retrieve_voter_guides_to_follow_generic_for_api(voter_id, search_string, filter_voter_guides_by_issue=False,
                                                    organization_we_vote_id_list_for_voter_issues=None,
                                                    maximum_number_to_retrieve=0, sort_by='', sort_order=''):
    """
    Separate from an election or a ballot item, return a list of voter_guides the voter has not already followed
    :param voter_id:
    :param search_string:
    :param filter_voter_guides_by_issue:
    :param organization_we_vote_id_list_for_voter_issues:
    :param maximum_number_to_retrieve:
    :param sort_by:
    :param sort_order:
    :return:
    """
    filter_voter_guides_by_issue = positive_value_exists(filter_voter_guides_by_issue)
    voter_guide_list_found = False

    # Start with orgs followed and ignored by this voter
    return_we_vote_id = True
    follow_organization_list_manager = FollowOrganizationList()
    if positive_value_exists(search_string):
        # If we are searching for organizations, we don't want to limit the search
        organization_we_vote_ids_followed_by_voter = []
        organization_we_vote_ids_ignored_by_voter = []
    else:
        organization_we_vote_ids_followed_by_voter = \
            follow_organization_list_manager.retrieve_follow_organization_by_voter_id_simple_id_array(voter_id,
                                                                                                      return_we_vote_id)
        organization_we_vote_ids_ignored_by_voter = \
            follow_organization_list_manager.retrieve_ignore_organization_by_voter_id_simple_id_array(
                voter_id, return_we_vote_id)

    # This is a list of orgs that the voter is already following or ignoring
    organization_we_vote_ids_followed_or_ignored_by_voter = list(chain(organization_we_vote_ids_followed_by_voter,
                                                                       organization_we_vote_ids_ignored_by_voter))

    voter_guide_list_manager = VoterGuideListManager()

    # First, retrieve the voter_guides stored by org and google_civic_election_id
    voter_guide_results = voter_guide_list_manager.retrieve_voter_guides_to_follow_generic(
        organization_we_vote_ids_followed_or_ignored_by_voter, search_string,
        maximum_number_to_retrieve, sort_by, sort_order)

    if voter_guide_results['voter_guide_list_found']:
        voter_guide_list = voter_guide_results['voter_guide_list']
    else:
        voter_guide_list = []

    position_list_manager = PositionListManager()
    if filter_voter_guides_by_issue and organization_we_vote_id_list_for_voter_issues is not None:
        voter_guide_list = position_list_manager.remove_positions_unrelated_to_issues(
            voter_guide_list, organization_we_vote_id_list_for_voter_issues)

    status = 'SUCCESSFUL_RETRIEVE_OF_VOTER_GUIDES_GENERIC '
    success = True

    if len(voter_guide_list):
        voter_guide_list_found = True

    results = {
        'success':                      success,
        'status':                       status,
        'voter_guide_list_found':       voter_guide_list_found,
        'voter_guide_list':             voter_guide_list,
    }
    return results


def voter_guide_save_for_api(voter_device_id, voter_guide_we_vote_id, google_civic_election_id):  # voterGuideSave
    """
    This function lets us create a new voter guide or update an existing one.
    :param voter_device_id:
    :param voter_guide_we_vote_id:
    :param google_civic_election_id:
    :return:
    """
    success = False
    status = ""
    voter_guide = VoterGuide()
    # organization = Organization()
    if not positive_value_exists(voter_device_id):
        status += 'VALID_VOTER_DEVICE_ID_MISSING'
        json_data = {
            'status':                       status,
            'success':                      False,
            'we_vote_id':                   voter_guide_we_vote_id,
            'google_civic_election_id':     google_civic_election_id,
            'time_span':                    "",
            'voter_guide_display_name':     "",
            'voter_guide_image_url_large':  "",
            'voter_guide_image_url_medium': "",
            'voter_guide_image_url_tiny':   "",
            'voter_guide_owner_type':       "",
            'organization_we_vote_id':      "",
            'public_figure_we_vote_id':     "",
            'twitter_description':          "",
            'twitter_followers_count':      0,
            'twitter_handle':               "",
            'owner_voter_id':               0,
            'pledge_goal':                  0,
            'pledge_count':                 0,
            'last_updated':                 "",
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    voter_manager = VoterManager()
    voter_results = voter_manager.retrieve_voter_from_voter_device_id(voter_device_id)
    voter_id = 0
    linked_organization_we_vote_id = ""
    if voter_results['voter_found']:
        voter = voter_results['voter']
        voter_id = voter.id
        linked_organization_we_vote_id = voter.linked_organization_we_vote_id
    if not positive_value_exists(voter_id):
        status += 'VALID_VOTER_ID_MISSING'
        json_data = {
            'status':                       status,
            'success':                      False,
            'we_vote_id':                   voter_guide_we_vote_id,
            'google_civic_election_id':     google_civic_election_id,
            'time_span':                    "",
            'voter_guide_display_name':     "",
            'voter_guide_image_url_large':  "",
            'voter_guide_image_url_medium': "",
            'voter_guide_image_url_tiny':   "",
            'voter_guide_owner_type':       "",
            'organization_we_vote_id':      linked_organization_we_vote_id,
            'public_figure_we_vote_id':     "",
            'twitter_description':          "",
            'twitter_followers_count':      0,
            'twitter_handle':               "",
            'owner_voter_id':               0,
            'pledge_goal':                  0,
            'pledge_count':                 0,
            'last_updated':                 "",
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    voter_guide_manager = VoterGuideManager()
    if positive_value_exists(voter_guide_we_vote_id):
        results = voter_guide_manager.retrieve_voter_guide(voter_guide_we_vote_id=voter_guide_we_vote_id)
        voter_guide_found = False
        status += results['status']
        if results['voter_guide_found']:
            voter_guide = results['voter_guide']
            if voter_guide.id:
                voter_guide_found = True
                success = True
        # If a voter_guide_we_vote_id is passed in and not found, we want to exit and NOT create a new one
        if not positive_value_exists(voter_guide_found):
            status += "VOTER_GUIDE_SAVE-VOTER_GUIDE_NOT_FOUND "
            json_data = {
                'status':                       status,
                'success':                      False,
                'we_vote_id':                   voter_guide_we_vote_id,
                'google_civic_election_id':     google_civic_election_id,
                'time_span':                    "",
                'voter_guide_display_name':     "",
                'voter_guide_image_url_large':  "",
                'voter_guide_image_url_medium': "",
                'voter_guide_image_url_tiny':   "",
                'voter_guide_owner_type':       "",
                'organization_we_vote_id':      linked_organization_we_vote_id,
                'public_figure_we_vote_id':     "",
                'twitter_description':          "",
                'twitter_followers_count':      0,
                'twitter_handle':               "",
                'owner_voter_id':               0,
                'pledge_goal':                  0,
                'pledge_count':                 0,
                'last_updated':                 "",
            }
            return HttpResponse(json.dumps(json_data), content_type='application/json')
    else:
        organization_manager = OrganizationManager()
        if positive_value_exists(linked_organization_we_vote_id):
            organization_results = \
                organization_manager.retrieve_organization_from_we_vote_id(linked_organization_we_vote_id)
            if organization_results['organization_found']:
                organization = organization_results['organization']
                linked_organization_we_vote_id = organization.we_vote_id
            else:
                organization_create_results = organization_manager.create_organization(
                    voter.get_full_name(), organization_website="", organization_twitter_handle="",
                    organization_type="INDIVIDUAL")
                if organization_create_results['organization_created']:
                    organization = organization_create_results['organization']
                    linked_organization_we_vote_id = organization.we_vote_id

        if not positive_value_exists(linked_organization_we_vote_id):
            status += 'LINKED_ORGANIZATION_NOT_FOUND '
            json_data = {
                'status':                       status,
                'success':                      False,
                'we_vote_id':                   voter_guide_we_vote_id,
                'google_civic_election_id':     google_civic_election_id,
                'time_span':                    "",
                'voter_guide_display_name':     "",
                'voter_guide_image_url_large':  "",
                'voter_guide_image_url_medium': "",
                'voter_guide_image_url_tiny':   "",
                'voter_guide_owner_type':       "",
                'organization_we_vote_id':      linked_organization_we_vote_id,
                'public_figure_we_vote_id':     "",
                'twitter_description':          "",
                'twitter_followers_count':      0,
                'twitter_handle':               "",
                'owner_voter_id':               0,
                'pledge_goal':                  0,
                'pledge_count':                 0,
                'last_updated':                 "",
            }
            return HttpResponse(json.dumps(json_data), content_type='application/json')

        results = voter_guide_manager.retrieve_voter_guide(google_civic_election_id=google_civic_election_id,
                                                           organization_we_vote_id=linked_organization_we_vote_id)
        voter_guide_found = False
        status += results['status']
        if results['voter_guide_found']:
            voter_guide = results['voter_guide']
            if voter_guide.id:
                voter_guide_found = True
                success = True

        if not voter_guide_found:
            create_results = voter_guide_manager.update_or_create_voter_voter_guide(
                google_civic_election_id=google_civic_election_id,
                voter=voter)
            if create_results['voter_guide_created'] or create_results['voter_guide_saved']:
                voter_guide_found = True
                success = True
                voter_guide = create_results['voter_guide']

    try:
        organization
    except NameError:
        organization_exists = False
    else:
        organization_exists = True

    if voter_guide_found and linked_organization_we_vote_id and organization_exists:
        refresh_results = voter_guide_manager.refresh_one_voter_guide_from_organization(voter_guide, organization)
        if refresh_results['values_changed']:
            voter_guide = refresh_results['voter_guide']
            try:
                voter_guide.save()
                success = True
                status += "VOTER_GUIDE_REFRESHED "
            except Exception as e:
                success = False
                status += "COULD_NOT_REFRESH_VOTER_GUIDE "

    json_data = {
        'status': status,
        'success': success,
        'we_vote_id': voter_guide.we_vote_id,
        'google_civic_election_id': voter_guide.google_civic_election_id,
        'time_span': voter_guide.vote_smart_time_span,
        'voter_guide_display_name': voter_guide.voter_guide_display_name(),
        'voter_guide_image_url_large': voter_guide.we_vote_hosted_profile_image_url_large
        if positive_value_exists(voter_guide.we_vote_hosted_profile_image_url_large)
        else voter_guide.voter_guide_image_url(),
        'voter_guide_image_url_medium': voter_guide.we_vote_hosted_profile_image_url_medium,
        'voter_guide_image_url_tiny': voter_guide.we_vote_hosted_profile_image_url_tiny,
        'voter_guide_owner_type': voter_guide.voter_guide_owner_type,
        'organization_we_vote_id': voter_guide.organization_we_vote_id,
        'public_figure_we_vote_id': voter_guide.public_figure_we_vote_id,
        'twitter_description': voter_guide.twitter_description,
        'twitter_followers_count': voter_guide.twitter_followers_count,
        'twitter_handle': voter_guide.twitter_handle,
        'owner_voter_id': voter_guide.owner_voter_id,
        'pledge_goal': voter_guide.pledge_goal,
        'pledge_count': voter_guide.pledge_count,
        'last_updated': voter_guide.last_updated.strftime('%Y-%m-%d %H:%M'),
    }
    return HttpResponse(json.dumps(json_data), content_type='application/json')


def voter_guides_followed_retrieve_for_api(voter_device_id, maximum_number_to_retrieve=0):
    """
    voter_guides_followed_retrieve_for_api(voter_device_id, maximum_number_to_retrieve=0)  # voterGuidesFollowedRetrieve
    Start with the organizations followed and return a list of voter_guides.
    See also organizations_followed_for_api, which returns a list of organizations.

    :param voter_device_id:
    :param maximum_number_to_retrieve:
    :return:
    """
    if not positive_value_exists(voter_device_id):
        json_data = {
            'status': 'VALID_VOTER_DEVICE_ID_MISSING',
            'success': False,
            'voter_device_id': voter_device_id,
            'maximum_number_to_retrieve': maximum_number_to_retrieve,
            'voter_guides': [],
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    voter_id = fetch_voter_id_from_voter_device_link(voter_device_id)
    if not positive_value_exists(voter_id):
        json_data = {
            'status': 'VALID_VOTER_ID_MISSING',
            'success': False,
            'voter_device_id': voter_device_id,
            'maximum_number_to_retrieve': maximum_number_to_retrieve,
            'voter_guides': [],
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    results = retrieve_voter_guides_followed(voter_id)
    status = results['status']
    voter_guide_list = results['voter_guide_list']
    voter_guides = []
    if results['voter_guide_list_found']:
        pledge_to_vote_manager = PledgeToVoteManager()
        voter_we_vote_id = fetch_voter_we_vote_id_from_voter_id(voter_id)
        number_added_to_list = 0
        for voter_guide in voter_guide_list:
            pledge_to_vote_we_vote_id = ""
            pledge_results = pledge_to_vote_manager.retrieve_pledge_to_vote(
                pledge_to_vote_we_vote_id, voter_we_vote_id, voter_guide.we_vote_id)
            if pledge_results['pledge_found']:
                voter_has_pledged = pledge_results['voter_has_pledged']
            else:
                voter_has_pledged = False
            one_voter_guide = {
                'we_vote_id':                   voter_guide.we_vote_id,
                'google_civic_election_id':     voter_guide.google_civic_election_id,
                'time_span':                    voter_guide.vote_smart_time_span,
                'voter_guide_display_name':     voter_guide.voter_guide_display_name(),
                'voter_guide_image_url_large':  voter_guide.we_vote_hosted_profile_image_url_large
                    if positive_value_exists(voter_guide.we_vote_hosted_profile_image_url_large)
                    else voter_guide.voter_guide_image_url(),
                'voter_guide_image_url_medium': voter_guide.we_vote_hosted_profile_image_url_medium,
                'voter_guide_image_url_tiny':   voter_guide.we_vote_hosted_profile_image_url_tiny,
                'voter_guide_owner_type':       voter_guide.voter_guide_owner_type,
                'organization_we_vote_id':      voter_guide.organization_we_vote_id,
                'public_figure_we_vote_id':     voter_guide.public_figure_we_vote_id,
                'twitter_description':          voter_guide.twitter_description,
                'twitter_followers_count':      voter_guide.twitter_followers_count,
                'twitter_handle':               voter_guide.twitter_handle,
                'owner_voter_id':               voter_guide.owner_voter_id,
                'pledge_goal':                  voter_guide.pledge_goal,
                'pledge_count':                 voter_guide.pledge_count,
                'voter_has_pledged':            voter_has_pledged,
                'last_updated':                 voter_guide.last_updated.strftime('%Y-%m-%d %H:%M'),
            }
            voter_guides.append(one_voter_guide.copy())
            # If we have passed in a limit (that is not zero), honor it
            if positive_value_exists(maximum_number_to_retrieve):
                number_added_to_list += 1
                if number_added_to_list >= maximum_number_to_retrieve:
                    break

        if len(voter_guides):
            status += 'VOTER_GUIDES_FOLLOWED_RETRIEVED '
            success = True
        else:
            status += 'NO_VOTER_GUIDES_FOLLOWED_FOUND '
            success = True
    else:
        success = False

    json_data = {
        'status': status,
        'success': success,
        'voter_device_id': voter_device_id,
        'maximum_number_to_retrieve': maximum_number_to_retrieve,
        'voter_guides': voter_guides,
    }
    return HttpResponse(json.dumps(json_data), content_type='application/json')


def voter_guides_retrieve_for_api(voter_device_id, organization_we_vote_id="", voter_we_vote_id="",
                                  maximum_number_to_retrieve=0):
    """
    voter_guides_retrieve_for_api(voter_device_id, maximum_number_to_retrieve=0)  # voterGuidesRetrieve
    This function allows us to search for voter guides using a variety of criteria.
    :param voter_device_id:
    :param organization_we_vote_id:
    :param voter_we_vote_id:
    :param maximum_number_to_retrieve:
    :return:
    """
    if not positive_value_exists(voter_device_id):
        json_data = {
            'status': 'VALID_VOTER_DEVICE_ID_MISSING',
            'success': False,
            'voter_device_id': voter_device_id,
            'maximum_number_to_retrieve': maximum_number_to_retrieve,
            'voter_guides': [],
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    voter_id = fetch_voter_id_from_voter_device_link(voter_device_id)
    if not positive_value_exists(voter_id):
        json_data = {
            'status': 'VALID_VOTER_ID_MISSING',
            'success': False,
            'voter_device_id': voter_device_id,
            'maximum_number_to_retrieve': maximum_number_to_retrieve,
            'voter_guides': [],
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    voter_guide_list_manager = VoterGuideListManager()
    results = voter_guide_list_manager.retrieve_all_voter_guides(organization_we_vote_id, 0, voter_we_vote_id)
    status = results['status']
    voter_guide_list = results['voter_guide_list']
    voter_guides = []
    if results['voter_guide_list_found']:
        number_added_to_list = 0
        for voter_guide in voter_guide_list:

            one_voter_guide = {
                'we_vote_id':                   voter_guide.we_vote_id,
                'google_civic_election_id':     voter_guide.google_civic_election_id,
                'election_day_text':            voter_guide.election_day_text,
                'time_span':                    voter_guide.vote_smart_time_span,
                'voter_guide_display_name':     voter_guide.voter_guide_display_name(),
                'voter_guide_image_url_large':  voter_guide.we_vote_hosted_profile_image_url_large
                if positive_value_exists(voter_guide.we_vote_hosted_profile_image_url_large)
                else voter_guide.voter_guide_image_url(),
                'voter_guide_image_url_medium': voter_guide.we_vote_hosted_profile_image_url_medium,
                'voter_guide_image_url_tiny':   voter_guide.we_vote_hosted_profile_image_url_tiny,
                'voter_guide_owner_type':       voter_guide.voter_guide_owner_type,
                'organization_we_vote_id':      voter_guide.organization_we_vote_id,
                'public_figure_we_vote_id':     voter_guide.public_figure_we_vote_id,
                'twitter_description':          voter_guide.twitter_description,
                'twitter_followers_count':      voter_guide.twitter_followers_count,
                'twitter_handle':               voter_guide.twitter_handle,
                'owner_voter_id':               voter_guide.owner_voter_id,
                'pledge_goal':                  voter_guide.pledge_goal,
                'pledge_count':                 voter_guide.pledge_count,
                'last_updated':                 voter_guide.last_updated.strftime('%Y-%m-%d %H:%M'),
            }
            voter_guides.append(one_voter_guide.copy())
            # If we have passed in a limit (that is not zero), honor it
            if positive_value_exists(maximum_number_to_retrieve):
                number_added_to_list += 1
                if number_added_to_list >= maximum_number_to_retrieve:
                    break

        if len(voter_guides):
            status += 'NO_VOTER_GUIDES_RETRIEVED '
            success = True
        else:
            status += 'NO_VOTER_GUIDE_LIST_FOUND1 '
            success = True
    else:
        status += 'NO_VOTER_GUIDE_LIST_FOUND2 '
        success = False

    json_data = {
        'status': status,
        'success': success,
        'voter_device_id': voter_device_id,
        'maximum_number_to_retrieve': maximum_number_to_retrieve,
        'voter_guides': voter_guides,
    }
    return HttpResponse(json.dumps(json_data), content_type='application/json')


def voter_follow_all_organizations_followed_by_organization_for_api(voter_device_id,
                                                                    organization_we_vote_id,
                                                                    maximum_number_to_follow=0,
                                                                    user_agent_string='', user_agent_object=None):
    # voterGuidesFollowedByOrganizationRetrieve
    """
    Retrieve organizations followed by organization_we_vote_id and follow all.

    :param voter_device_id:
    :param organization_we_vote_id:
    :param maximum_number_to_follow:
    :param user_agent_string:
    :param user_agent_object:
    :return:
    """
    if not positive_value_exists(voter_device_id):
        json_data = {
            'status':                       'VALID_VOTER_DEVICE_ID_MISSING',
            'success':                      False,
            'voter_device_id':              voter_device_id,
            'maximum_number_to_follow':     maximum_number_to_follow,
            'voter_guides':                 [],
            'organization_we_vote_id':      organization_we_vote_id,
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    voter_id = fetch_voter_id_from_voter_device_link(voter_device_id)
    if not positive_value_exists(voter_id):
        json_data = {
            'status':                       'VALID_VOTER_ID_MISSING',
            'success':                      False,
            'voter_device_id':              voter_device_id,
            'maximum_number_to_follow':     maximum_number_to_follow,
            'voter_guides':                 [],
            'organization_we_vote_id':      organization_we_vote_id,
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    voter_manager = VoterManager()
    voter_results = voter_manager.retrieve_voter_by_id(voter_id)
    if not voter_results['voter_found']:
        json_data = {
            'status':                       'VOTER_NOT_FOUND',
            'success':                      False,
            'voter_device_id':              voter_device_id,
            'maximum_number_to_follow':     maximum_number_to_follow,
            'voter_guides':                 [],
            'organization_we_vote_id':      organization_we_vote_id,
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    if not positive_value_exists(organization_we_vote_id):
        json_data = {
            'status':                       'ORGANIZATION_WE_VOTE_ID_MISSING',
            'success':                      False,
            'voter_device_id':              voter_device_id,
            'maximum_number_to_follow':     maximum_number_to_follow,
            'voter_guides':                 [],
            'organization_we_vote_id':      organization_we_vote_id,
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    # Retrieve all organizations already followed by voter
    organizations_followed_by_voter_results = retrieve_organizations_followed_by_organization_we_vote_id(
        voter_results['voter'].linked_organization_we_vote_id)
    organizations_we_vote_ids_list_followed_by_voter = \
        organizations_followed_by_voter_results['organization_we_vote_ids_followed_list']

    # Retrieve all organizations followed by this organization
    organizations_followed_by_we_vote_id_results = retrieve_organizations_followed_by_organization_we_vote_id(
        organization_we_vote_id)
    organizations_we_vote_ids_list_followed_by_organization_we_vote_id = \
        organizations_followed_by_we_vote_id_results['organization_we_vote_ids_followed_list']

    # If some organizations are already followed by voter then do not follow again.
    organization_we_vote_ids_list_need_to_be_followed = []
    for organization_followed_by_we_vote_id in organizations_we_vote_ids_list_followed_by_organization_we_vote_id:
        if organization_followed_by_we_vote_id not in organizations_we_vote_ids_list_followed_by_voter:
            organization_we_vote_ids_list_need_to_be_followed.append(organization_followed_by_we_vote_id)

    success = True
    status = organizations_followed_by_we_vote_id_results['status']
    organizations_follow_all_results = []
    if len(organization_we_vote_ids_list_need_to_be_followed):
        number_added_to_list = 0
        for organization_we_vote_id_followed in organization_we_vote_ids_list_need_to_be_followed:
            organization_follow_result = organization_follow_or_unfollow_or_ignore(
                voter_device_id, organization_id=0, organization_we_vote_id=organization_we_vote_id_followed,
                follow_kind=FOLLOWING, user_agent_string=user_agent_string, user_agent_object=user_agent_object)
            if not organization_follow_result['success']:
                success = False

            organizations_follow_all_results.append(organization_follow_result)
            if positive_value_exists(maximum_number_to_follow):
                number_added_to_list += 1
                if number_added_to_list >= maximum_number_to_follow:
                    break

    json_data = {
        'status':                           status,
        'success':                          success,
        'voter_device_id':                  voter_device_id,
        'maximum_number_to_follow':         maximum_number_to_follow,
        'organizations_follow_all_results': organizations_follow_all_results,
        'organization_we_vote_id':          organization_we_vote_id,
    }
    return HttpResponse(json.dumps(json_data), content_type='application/json')


def voter_guides_followed_by_organization_retrieve_for_api(voter_device_id,  # voterGuidesFollowedByOrganizationRetrieve
                                                           voter_linked_organization_we_vote_id,
                                                           filter_by_this_google_civic_election_id=False,
                                                           maximum_number_to_retrieve=0):
    """
    Start with the organizations followed and return a list of voter_guides. voterGuidesFollowedByOrganizationRetrieve
    See also organizations_followed_for_api, which returns a list of organizations.

    :param voter_device_id:
    :param voter_linked_organization_we_vote_id:
    :param filter_by_this_google_civic_election_id:
    :param maximum_number_to_retrieve:
    :return:
    """
    status = ""
    if not positive_value_exists(voter_device_id):
        json_data = {
            'status':                       'VALID_VOTER_DEVICE_ID_MISSING',
            'success':                      False,
            'voter_device_id':              voter_device_id,
            'maximum_number_to_retrieve':   maximum_number_to_retrieve,
            'voter_guides':                 [],
            'organization_we_vote_id':      voter_linked_organization_we_vote_id,
            'filter_by_this_google_civic_election_id':  filter_by_this_google_civic_election_id
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    voter_id = fetch_voter_id_from_voter_device_link(voter_device_id)
    if not positive_value_exists(voter_id):
        json_data = {
            'status':                       'VALID_VOTER_ID_MISSING',
            'success':                      False,
            'voter_device_id':              voter_device_id,
            'maximum_number_to_retrieve':   maximum_number_to_retrieve,
            'voter_guides':                 [],
            'organization_we_vote_id':      voter_linked_organization_we_vote_id,
            'filter_by_this_google_civic_election_id':  filter_by_this_google_civic_election_id
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    voter_manager = VoterManager()
    results = voter_manager.retrieve_voter_by_id(voter_id)
    status += results['status'] + 'VOTER_NOT_FOUND'
    if not results['voter_found']:
        json_data = {
            'status':                       status,
            'success':                      False,
            'voter_device_id':              voter_device_id,
            'maximum_number_to_retrieve':   maximum_number_to_retrieve,
            'voter_guides':                 [],
            'organization_we_vote_id':      voter_linked_organization_we_vote_id,
            'filter_by_this_google_civic_election_id':  filter_by_this_google_civic_election_id
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    voter = results['voter']
    voter_we_vote_id = voter.we_vote_id
    results = retrieve_voter_guides_followed_by_organization_we_vote_id(voter_linked_organization_we_vote_id,
                                                                        filter_by_this_google_civic_election_id)
    status += results['status']
    voter_guide_list = results['voter_guide_list']
    voter_guides = []
    if results['voter_guide_list_found']:
        pledge_to_vote_manager = PledgeToVoteManager()
        number_added_to_list = 0
        for voter_guide in voter_guide_list:
            pledge_to_vote_we_vote_id = ""
            pledge_results = pledge_to_vote_manager.retrieve_pledge_to_vote(
                pledge_to_vote_we_vote_id, voter_we_vote_id, voter_guide.we_vote_id)
            if pledge_results['pledge_found']:
                voter_has_pledged = pledge_results['voter_has_pledged']
            else:
                voter_has_pledged = False
            one_voter_guide = {
                'we_vote_id':                   voter_guide.we_vote_id,
                'google_civic_election_id':     voter_guide.google_civic_election_id,
                'time_span':                    voter_guide.vote_smart_time_span,
                'voter_guide_display_name':     voter_guide.voter_guide_display_name(),
                'voter_guide_image_url_large':  voter_guide.we_vote_hosted_profile_image_url_large
                    if positive_value_exists(voter_guide.we_vote_hosted_profile_image_url_large)
                    else voter_guide.voter_guide_image_url(),
                'voter_guide_image_url_medium': voter_guide.we_vote_hosted_profile_image_url_medium,
                'voter_guide_image_url_tiny':   voter_guide.we_vote_hosted_profile_image_url_tiny,
                'voter_guide_owner_type':       voter_guide.voter_guide_owner_type,
                'organization_we_vote_id':      voter_guide.organization_we_vote_id,
                'public_figure_we_vote_id':     voter_guide.public_figure_we_vote_id,
                'twitter_description':          voter_guide.twitter_description,
                'twitter_followers_count':      voter_guide.twitter_followers_count,
                'twitter_handle':               voter_guide.twitter_handle,
                'owner_voter_id':               voter_guide.owner_voter_id,
                'pledge_goal':                  voter_guide.pledge_goal,
                'pledge_count':                 voter_guide.pledge_count,
                'voter_has_pledged':            voter_has_pledged,
                'last_updated':                 voter_guide.last_updated.strftime('%Y-%m-%d %H:%M'),
            }
            voter_guides.append(one_voter_guide.copy())
            if positive_value_exists(maximum_number_to_retrieve):
                number_added_to_list += 1
                if number_added_to_list >= maximum_number_to_retrieve:
                    break

        if len(voter_guides):
            status += 'VOTER_GUIDES_FOLLOWED_BY_ORGANIZATION_RETRIEVED '
            success = True
        else:
            status += 'NO_VOTER_GUIDES_FOLLOWED_BY_ORGANIZATION_FOUND '
            success = True
    else:
        success = False

    json_data = {
        'status':                       status,
        'success':                      success,
        'voter_device_id':              voter_device_id,
        'maximum_number_to_retrieve':   maximum_number_to_retrieve,
        'voter_guides':                 voter_guides,
        'organization_we_vote_id':      voter_linked_organization_we_vote_id,
        'filter_by_this_google_civic_election_id':  filter_by_this_google_civic_election_id
    }
    return HttpResponse(json.dumps(json_data), content_type='application/json')


def voter_guide_followers_retrieve_for_api(voter_device_id, organization_we_vote_id,  # voterGuideFollowersRetrieve
                                           maximum_number_to_retrieve=0):
    """
    Start with the organizations followed and return a list of voter_guides. voterGuidesFollowedByOrganizationRetrieve
    See also organizations_followed_for_api, which returns a list of organizations.

    :param voter_device_id:
    :param organization_we_vote_id:
    :param maximum_number_to_retrieve:
    :return:
    """
    if not positive_value_exists(voter_device_id):
        json_data = {
            'status':                       'VALID_VOTER_DEVICE_ID_MISSING',
            'success':                      False,
            'voter_device_id':              voter_device_id,
            'organization_we_vote_id':      organization_we_vote_id,
            'maximum_number_to_retrieve':   maximum_number_to_retrieve,
            'voter_guides':                 [],
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    voter_id = fetch_voter_id_from_voter_device_link(voter_device_id)
    if not positive_value_exists(voter_id):
        json_data = {
            'status':                       'VALID_VOTER_ID_MISSING',
            'success':                      False,
            'voter_device_id':              voter_device_id,
            'organization_we_vote_id':      organization_we_vote_id,
            'maximum_number_to_retrieve':   maximum_number_to_retrieve,
            'voter_guides':                 [],
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    voter_manager = VoterManager()
    results = voter_manager.retrieve_voter_by_id(voter_id)
    if not results['voter_found']:
        json_data = {
            'status':                       'VOTER_NOT_FOUND',
            'success':                      False,
            'voter_device_id':              voter_device_id,
            'organization_we_vote_id':      organization_we_vote_id,
            'maximum_number_to_retrieve':   maximum_number_to_retrieve,
            'voter_guides':                 [],
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    results = retrieve_voter_guide_followers_by_organization_we_vote_id(organization_we_vote_id)
    status = results['status']
    voter_guides = []
    if results['organization_list_found']:
        organization_list = results['organization_list']
        number_added_to_list = 0
        for one_organization in organization_list:
            if not positive_value_exists(one_organization.organization_name):
                continue
            elif one_organization.organization_name.startswith("Voter-"):
                continue

            date_last_changed = one_organization.date_last_changed
            if positive_value_exists(date_last_changed):
                last_updated = date_last_changed.strftime('%Y-%m-%d %H:%M')
            else:
                last_updated = ""
            # pledge_to_vote_manager = PledgeToVoteManager()
            # pledge_results = pledge_to_vote_manager.retrieve_pledge_statistics()
            # TODO We don't have a voter_guide_we_vote_id here so it is hard to get the right pledge_statistics
            one_voter_guide = {
                'voter_guide_display_name':     one_organization.organization_name,
                'voter_guide_image_url_large':  one_organization.we_vote_hosted_profile_image_url_large
                if positive_value_exists(one_organization.we_vote_hosted_profile_image_url_large)
                else one_organization.organization_photo_url(),
                'voter_guide_image_url_medium': one_organization.we_vote_hosted_profile_image_url_medium,
                'voter_guide_image_url_tiny':   one_organization.we_vote_hosted_profile_image_url_tiny,
                'organization_we_vote_id':      one_organization.we_vote_id,
                'twitter_description':          one_organization.twitter_description,
                'twitter_followers_count':      one_organization.twitter_followers_count,
                'twitter_handle':               one_organization.organization_twitter_handle,
                # 'pledge_goal':                  pledge_goal,
                # 'pledge_count':                 pledge_count,
                'last_updated':                 last_updated,
            }
            voter_guides.append(one_voter_guide.copy())
            if positive_value_exists(maximum_number_to_retrieve):
                number_added_to_list += 1
                if number_added_to_list >= maximum_number_to_retrieve:
                    break

        if len(voter_guides):
            status += 'VOTER_GUIDE_FOLLOWERS_RETRIEVED '
            success = True
        else:
            status += 'NO_VOTER_GUIDE_FOLLOWERS_FOUND '
            success = True
    else:
        success = False

    json_data = {
        'status':                       status,
        'success':                      success,
        'voter_device_id':              voter_device_id,
        'organization_we_vote_id':      organization_we_vote_id,
        'maximum_number_to_retrieve':   maximum_number_to_retrieve,
        'voter_guides':                 voter_guides,
    }
    return HttpResponse(json.dumps(json_data), content_type='application/json')


def refresh_existing_voter_guides(google_civic_election_id, organization_we_vote_id=""):
    voter_guide_updated_count = 0
    voter_guide_list_found = False
    voter_guide_list = []
    status = ""
    success = True

    # Cycle through existing voter_guides
    voter_guide_list_manager = VoterGuideListManager()
    voter_guide_manager = VoterGuideManager()

    if positive_value_exists(organization_we_vote_id) and positive_value_exists(google_civic_election_id):
        voter_guide_we_vote_id = ''
        results = voter_guide_manager.update_or_create_organization_voter_guide_by_election_id(
            voter_guide_we_vote_id, organization_we_vote_id, google_civic_election_id)
        if results['voter_guide_saved']:
            voter_guide_list_found = True
            voter_guide_list.append(results['voter_guide'])
    elif positive_value_exists(organization_we_vote_id):
        results = voter_guide_list_manager.retrieve_all_voter_guides_by_organization_we_vote_id(organization_we_vote_id)
        if results['voter_guide_list_found']:
            voter_guide_list_found = True
            voter_guide_list = results['voter_guide_list']
    elif positive_value_exists(google_civic_election_id):
        results = voter_guide_list_manager.retrieve_voter_guides_for_election(google_civic_election_id)
        if results['voter_guide_list_found']:
            voter_guide_list_found = True
            voter_guide_list = results['voter_guide_list']
    else:
        results = voter_guide_list_manager.retrieve_all_voter_guides_order_by()
        if results['voter_guide_list_found']:
            voter_guide_list_found = True
            voter_guide_list = results['voter_guide_list']

    if voter_guide_list_found:
        for voter_guide in voter_guide_list:
            if positive_value_exists(voter_guide.organization_we_vote_id):
                results = refresh_organization_data_from_master_tables(voter_guide.organization_we_vote_id)
                status += results['status']
                # DALE 2017-11-06 This seems to be wasteful, doing the same data pushing multiple times. Refactor.
                if results['success']:
                    push_organization_data_to_other_table_caches(voter_guide.organization_we_vote_id)
                # DALE 2017-11-06 The update voter guides functions below I think are also done
                #  in "push_organization_data_to_other_table_caches". Refactor.
                if positive_value_exists(voter_guide.google_civic_election_id):
                    voter_guide_we_vote_id = ''
                    results = voter_guide_manager.update_or_create_organization_voter_guide_by_election_id(
                        voter_guide_we_vote_id,
                        voter_guide.organization_we_vote_id, voter_guide.google_civic_election_id)
                    if results['success']:
                        voter_guide_updated_count += 1
                elif positive_value_exists(voter_guide.vote_smart_time_span):
                    voter_guide_we_vote_id = ''
                    results = voter_guide_manager.update_or_create_organization_voter_guide_by_time_span(
                        voter_guide_we_vote_id, voter_guide.organization_we_vote_id, voter_guide.vote_smart_time_span)
                    if results['success']:
                        voter_guide_updated_count += 1
    results = {
        'status':                       status,
        'success':                      success,
        'voter_guide_updated_count':    voter_guide_updated_count,
        'voter_guide_list_found':       voter_guide_list_found,
        'voter_guide_list':             voter_guide_list,
    }
    return results


def retrieve_organizations_followed_by_organization_we_vote_id(organization_we_vote_id):
    # voterFollowAllOrganizationsFollowedByOrganization
    """
    Retrieve organizations_we_vote_ids_list followed_by_organization_we_vote_id.
    :param organization_we_vote_id:
    :return:
    """

    follow_organization_list_manager = FollowOrganizationList()
    return_we_vote_id = True
    organization_we_vote_ids_followed_list = \
        follow_organization_list_manager.retrieve_followed_organization_by_organization_we_vote_id_simple_id_array(
            organization_we_vote_id, return_we_vote_id)

    if len(organization_we_vote_ids_followed_list):
        status = 'SUCCESSFUL_RETRIEVE_OF_ORGANIZATIONS_FOLLOWED'
        organization_we_vote_ids_followed_list_found = True
    else:
        status = 'ORGANIZATIONS_FOLLOWED_NOT_FOUND'
        organization_we_vote_ids_followed_list_found = False

    results = {
        'status':                                       status,
        'organization_we_vote_ids_followed_list_found': organization_we_vote_ids_followed_list_found,
        'organization_we_vote_ids_followed_list':       organization_we_vote_ids_followed_list,
    }
    return results


def retrieve_voter_guides_followed(voter_id):
    voter_guide_list_found = False

    follow_organization_list_manager = FollowOrganizationList()
    return_we_vote_id = True
    organization_we_vote_ids_followed_by_voter = \
        follow_organization_list_manager.retrieve_follow_organization_by_voter_id_simple_id_array(voter_id,
                                                                                                  return_we_vote_id)

    voter_guide_list_object = VoterGuideListManager()
    results = voter_guide_list_object.retrieve_voter_guides_by_organization_list(
        organization_we_vote_ids_followed_by_voter)

    voter_guide_list = []
    if results['voter_guide_list_found']:
        voter_guide_list = results['voter_guide_list']
        status = 'SUCCESSFUL_RETRIEVE_OF_VOTER_GUIDES_FOLLOWED'
        success = True
        if len(voter_guide_list):
            voter_guide_list_found = True
    else:
        status = results['status']
        success = False

    results = {
        'success':                      success,
        'status':                       status,
        'voter_guide_list_found':       voter_guide_list_found,
        'voter_guide_list':             voter_guide_list,
    }
    return results


def retrieve_voter_guides_followed_by_organization_we_vote_id(organization_we_vote_id,
                                                              filter_by_this_google_civic_election_id=False):
    # retrieve_voter_guides_followed_by_organization_we_vote_id() voterGuidesFollowedByOrganizationRetrieve
    """
    Retrieve voter guide followed by an organization with organization_we_vote_id
    :param organization_we_vote_id:
    :param filter_by_this_google_civic_election_id:
    :return:
    """
    voter_guide_list_found = False

    follow_organization_list_manager = FollowOrganizationList()
    return_we_vote_id = True
    organization_we_vote_ids_followed = \
        follow_organization_list_manager.retrieve_followed_organization_by_organization_we_vote_id_simple_id_array(
            organization_we_vote_id, return_we_vote_id)

    voter_guide_list_object = VoterGuideListManager()
    results = voter_guide_list_object.retrieve_voter_guides_by_organization_list(
        organization_we_vote_ids_followed, filter_by_this_google_civic_election_id)

    voter_guide_list = []
    if results['voter_guide_list_found']:
        voter_guide_list = results['voter_guide_list']
        status = 'SUCCESSFUL_RETRIEVE_OF_VOTER_GUIDES_FOLLOWED'
        success = True
        if len(voter_guide_list):
            voter_guide_list_found = True
    else:
        status = results['status']
        success = False

    results = {
        'success':                      success,
        'status':                       status,
        'voter_guide_list_found':       voter_guide_list_found,
        'voter_guide_list':             voter_guide_list,
    }
    return results


def retrieve_voter_guide_followers_by_organization_we_vote_id(organization_we_vote_id):  # voterGuidesFollowersRetrieve
    organization_list_found = False

    follow_organization_list_manager = FollowOrganizationList()
    return_we_vote_id = True
    organization_we_vote_ids_followers = \
        follow_organization_list_manager.retrieve_followers_organization_by_organization_we_vote_id_simple_id_array(
            organization_we_vote_id, return_we_vote_id)

    organization_list_object = OrganizationListManager()
    results = organization_list_object.retrieve_organizations_by_organization_we_vote_id_list(
        organization_we_vote_ids_followers)

    organization_list = []
    if results['organization_list_found']:
        organization_list = results['organization_list']
        status = 'SUCCESSFUL_RETRIEVE_OF_ORGANIZATIONS_FOLLOWERS'
        success = True
        if len(organization_list):
            organization_list_found = True
    else:
        status = results['status']
        success = False

    results = {
        'success':                      success,
        'status':                       status,
        'organization_list_found':      organization_list_found,
        'organization_list':            organization_list,
    }
    return results


def voter_guides_ignored_retrieve_for_api(voter_device_id, maximum_number_to_retrieve=0):
    """
    Start with the organizations followed and return a list of voter_guides. voterGuidesIgnoredRetrieve
    See also organizations_followed_for_api, which returns a list of organizations.

    :param voter_device_id:
    :param maximum_number_to_retrieve:
    :return:
    """
    if not positive_value_exists(voter_device_id):
        json_data = {
            'status': 'VALID_VOTER_DEVICE_ID_MISSING',
            'success': False,
            'voter_device_id': voter_device_id,
            'maximum_number_to_retrieve': maximum_number_to_retrieve,
            'voter_guides': [],
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')

    voter_id = fetch_voter_id_from_voter_device_link(voter_device_id)
    if not positive_value_exists(voter_id):
        json_data = {
            'status': 'VALID_VOTER_ID_MISSING',
            'success': False,
            'voter_device_id': voter_device_id,
            'maximum_number_to_retrieve': maximum_number_to_retrieve,
            'voter_guides': [],
        }
        return HttpResponse(json.dumps(json_data), content_type='application/json')
    voter_manager = VoterManager()
    results = voter_manager.retrieve_voter_by_id(voter_id)
    if results['voter_found']:
        voter = results['voter']
        voter_we_vote_id = voter.we_vote_id
    else:
        voter_we_vote_id = ""

    results = retrieve_voter_guides_ignored(voter_id)
    status = results['status']
    voter_guide_list = results['voter_guide_list']
    voter_guides = []
    if results['voter_guide_list_found']:
        number_added_to_list = 0
        pledge_to_vote_manager = PledgeToVoteManager()
        for voter_guide in voter_guide_list:
            pledge_to_vote_we_vote_id = ""
            pledge_results = pledge_to_vote_manager.retrieve_pledge_to_vote(
                pledge_to_vote_we_vote_id, voter_we_vote_id, voter_guide.we_vote_id)
            if pledge_results['pledge_found']:
                voter_has_pledged = pledge_results['voter_has_pledged']
            else:
                voter_has_pledged = False
            one_voter_guide = {
                'we_vote_id':                   voter_guide.we_vote_id,
                'google_civic_election_id':     voter_guide.google_civic_election_id,
                'time_span':                    voter_guide.vote_smart_time_span,
                'voter_guide_display_name':     voter_guide.voter_guide_display_name(),
                'voter_guide_image_url_large':  voter_guide.we_vote_hosted_profile_image_url_large
                    if positive_value_exists(voter_guide.we_vote_hosted_profile_image_url_large)
                    else voter_guide.voter_guide_image_url(),
                'voter_guide_image_url_medium': voter_guide.we_vote_hosted_profile_image_url_medium,
                'voter_guide_image_url_tiny':   voter_guide.we_vote_hosted_profile_image_url_tiny,
                'voter_guide_owner_type':       voter_guide.voter_guide_owner_type,
                'organization_we_vote_id':      voter_guide.organization_we_vote_id,
                'public_figure_we_vote_id':     voter_guide.public_figure_we_vote_id,
                'twitter_description':          voter_guide.twitter_description,
                'twitter_followers_count':      voter_guide.twitter_followers_count,
                'twitter_handle':               voter_guide.twitter_handle,
                'owner_voter_id':               voter_guide.owner_voter_id,
                'pledge_goal':                  voter_guide.pledge_goal,
                'pledge_count':                 voter_guide.pledge_count,
                'voter_has_pledged':            voter_has_pledged,
                'last_updated':                 voter_guide.last_updated.strftime('%Y-%m-%d %H:%M'),
            }
            voter_guides.append(one_voter_guide.copy())
            if positive_value_exists(maximum_number_to_retrieve):
                number_added_to_list += 1
                if number_added_to_list >= maximum_number_to_retrieve:
                    break

        if len(voter_guides):
            status = 'VOTER_GUIDES_IGNORED_RETRIEVED'
            success = True
        else:
            status = 'NO_VOTER_GUIDES_IGNORED_FOUND'
            success = True
    else:
        success = False

    json_data = {
        'status': status,
        'success': success,
        'voter_device_id': voter_device_id,
        'maximum_number_to_retrieve': maximum_number_to_retrieve,
        'voter_guides': voter_guides,
    }
    return HttpResponse(json.dumps(json_data), content_type='application/json')


def retrieve_voter_guides_ignored(voter_id):  # voterGuidesIgnoredRetrieve
    voter_guide_list_found = False

    follow_organization_list_manager = FollowOrganizationList()
    return_we_vote_id = True
    organization_we_vote_ids_ignored_by_voter = \
        follow_organization_list_manager.retrieve_ignore_organization_by_voter_id_simple_id_array(voter_id,
                                                                                                  return_we_vote_id)

    voter_guide_list_object = VoterGuideListManager()
    results = voter_guide_list_object.retrieve_voter_guides_by_organization_list(
        organization_we_vote_ids_ignored_by_voter)

    voter_guide_list = []
    if results['voter_guide_list_found']:
        voter_guide_list = results['voter_guide_list']
        status = 'SUCCESSFUL_RETRIEVE_OF_VOTER_GUIDES_IGNORED'
        success = True
        if len(voter_guide_list):
            voter_guide_list_found = True
    else:
        status = results['status']
        success = False

    results = {
        'success':                      success,
        'status':                       status,
        'voter_guide_list_found':       voter_guide_list_found,
        'voter_guide_list':             voter_guide_list,
    }
    return results
