# import_export_twitter/controllers.py
# Brought to you by We Vote. Be good.
# -*- coding: UTF-8 -*-

# See also WeVoteServer/twitter/controllers.py for routines that manage internal twitter data
import re
import tweepy
import urllib.request
import wevote_functions.admin
from candidate.controllers import refresh_candidate_data_from_master_tables
from candidate.models import CandidateCampaignManager, CandidateCampaignListManager
from config.base import get_environment_variable
from image.controllers import TWITTER, cache_master_and_resized_image
from image.models import WeVoteImageManager
from import_export_twitter.models import TwitterAuthManager
from organization.controllers import move_organization_to_another_complete, \
    update_social_media_statistics_in_other_tables
from organization.models import Organization, OrganizationListManager, OrganizationManager, INDIVIDUAL
from politician.models import PoliticianManager
from position.controllers import update_all_position_details_from_candidate, \
    update_position_entered_details_from_organization, update_position_for_friends_details_from_voter
from socket import timeout
from twitter.functions import retrieve_twitter_user_info
from twitter.models import TwitterUserManager
from voter.models import VoterManager
from voter_guide.models import VoterGuideListManager
from wevote_functions.functions import convert_to_int, extract_twitter_handle_from_text_string, \
    is_voter_device_id_valid, positive_value_exists

logger = wevote_functions.admin.get_logger(__name__)


WE_VOTE_SERVER_ROOT_URL = get_environment_variable("WE_VOTE_SERVER_ROOT_URL")

RE_FACEBOOK = r'//www\.twitter\.com/(?:#!/)?(\w+)'
# RE_FACEBOOK = r'/(?:https?:\/\/)?(?:www\.)?facebook\.com\/(?:(?:\w)*#!\/)?(?:pages\/)?(?:[\w\-]*\/)*?(\/)?([^/?]*)/'
FACEBOOK_BLACKLIST = ['group', 'group.php', 'None']
# NOTE: Scraping a website for the Facebook handle is more complicated than Twitter. There must be an existing
#  solution available? My attempt turned off for now.

# Only pays attention to https://twitter.com or http://twitter.com and ignores www.twitter.com
RE_TWITTER = r'//twitter\.com/(?:#!/)?(\w+)'
TWITTER_BLACKLIST = ['home', 'https', 'intent', 'none', 'search', 'share', 'twitterapi']
TWITTER_CONSUMER_KEY = get_environment_variable("TWITTER_CONSUMER_KEY")
TWITTER_CONSUMER_SECRET = get_environment_variable("TWITTER_CONSUMER_SECRET")
TWITTER_ACCESS_TOKEN = get_environment_variable("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = get_environment_variable("TWITTER_ACCESS_TOKEN_SECRET")
TWITTER_NATIVE_INDICATOR = 'native'


class FakeFirefoxURLopener(urllib.request.FancyURLopener):
    version = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.9; rv:25.0)' \
            + ' Gecko/20100101 Firefox/25.0'


class GetOutOfLoop(Exception):
    pass


class GetOutOfLoopLocal(Exception):
    pass


def refresh_twitter_candidate_details(candidate_campaign):
    status = ""
    candidate_campaign_manager = CandidateCampaignManager()
    politician_manager = PoliticianManager()
    twitter_user_manager = TwitterUserManager()
    we_vote_image_manager = WeVoteImageManager()

    if not candidate_campaign:
        status += "TWITTER_CANDIDATE_DETAILS_NOT_RETRIEVED-CANDIDATE_MISSING "
        results = {
            'success':                  False,
            'status':                   status,
        }
        return results

    if candidate_campaign.candidate_twitter_handle:
        status += "TWITTER_CANDIDATE_DETAILS-REACHING_OUT_TO_TWITTER "
        twitter_user_id = 0
        results = retrieve_twitter_user_info(twitter_user_id, candidate_campaign.candidate_twitter_handle)

        if results['success']:
            status += "TWITTER_CANDIDATE_DETAILS_RETRIEVED_FROM_TWITTER "

            # Get original image url for cache original size image
            twitter_profile_image_url_https = we_vote_image_manager.twitter_profile_image_url_https_original(
                results['twitter_json']['profile_image_url_https'])
            twitter_profile_background_image_url_https = results['twitter_json']['profile_background_image_url_https'] \
                if 'profile_background_image_url_https' in results['twitter_json'] else None
            twitter_profile_banner_url_https = results['twitter_json']['profile_banner_url'] \
                if 'profile_banner_url' in results['twitter_json'] else None
            cache_results = cache_master_and_resized_image(
                candidate_id=candidate_campaign.id, candidate_we_vote_id=candidate_campaign.we_vote_id,
                twitter_id=candidate_campaign.twitter_user_id,
                twitter_screen_name=candidate_campaign.candidate_twitter_handle,
                twitter_profile_image_url_https=twitter_profile_image_url_https,
                twitter_profile_background_image_url_https=twitter_profile_background_image_url_https,
                twitter_profile_banner_url_https=twitter_profile_banner_url_https, image_source=TWITTER)
            cached_twitter_profile_image_url_https = cache_results['cached_twitter_profile_image_url_https']
            cached_twitter_profile_background_image_url_https = \
                cache_results['cached_twitter_profile_background_image_url_https']
            cached_twitter_profile_banner_url_https = cache_results['cached_twitter_profile_banner_url_https']
            we_vote_hosted_profile_image_url_large = cache_results['we_vote_hosted_profile_image_url_large']
            we_vote_hosted_profile_image_url_medium = cache_results['we_vote_hosted_profile_image_url_medium']
            we_vote_hosted_profile_image_url_tiny = cache_results['we_vote_hosted_profile_image_url_tiny']

            save_candidate_campaign_results = candidate_campaign_manager.update_candidate_twitter_details(
                candidate_campaign, results['twitter_json'], cached_twitter_profile_image_url_https,
                cached_twitter_profile_background_image_url_https, cached_twitter_profile_banner_url_https,
                we_vote_hosted_profile_image_url_large, we_vote_hosted_profile_image_url_medium,
                we_vote_hosted_profile_image_url_tiny)
            candidate_campaign = save_candidate_campaign_results['candidate']
            save_twitter_user_results = twitter_user_manager.update_or_create_twitter_user(
                results['twitter_json'], candidate_campaign.twitter_user_id, cached_twitter_profile_image_url_https,
                cached_twitter_profile_background_image_url_https, cached_twitter_profile_banner_url_https,
                we_vote_hosted_profile_image_url_large, we_vote_hosted_profile_image_url_medium,
                we_vote_hosted_profile_image_url_tiny)
            # Need to update voter twitter details for the candidate in future
            save_politician_details_results = politician_manager.update_politician_details_from_candidate(
                candidate_campaign)
            save_position_from_candidate_results = update_all_position_details_from_candidate(candidate_campaign)
    else:
        status += "TWITTER_CANDIDATE_DETAILS-CLEARING_DETAILS "
        save_candidate_campaign_results = candidate_campaign_manager.clear_candidate_twitter_details(candidate_campaign)

    results = {
        'success':                  True,
        'status':                   status,
    }
    return results


def refresh_twitter_organization_details(organization, twitter_user_id=0):
    """
    This function assumes TwitterLinkToOrganization is happening outside of this function. It relies on our caching
    organization_twitter_handle in the organization object.
    :param organization:
    :param twitter_user_id:
    :return:
    """
    organization_manager = OrganizationManager()
    twitter_user_manager = TwitterUserManager()
    voter_manager = VoterManager()
    we_vote_image_manager = WeVoteImageManager()
    status = ""
    organization_twitter_handle = ""
    cached_twitter_profile_image_url_https = None
    cached_twitter_profile_background_image_url_https = None
    cached_twitter_profile_banner_url_https = None
    we_vote_hosted_profile_image_url_large = None
    we_vote_hosted_profile_image_url_medium = None
    we_vote_hosted_profile_image_url_tiny = None

    if not organization:
        status += "ORGANIZATION_TWITTER_DETAILS_NOT_RETRIEVED-ORG_MISSING "
        results = {
            'success':          False,
            'status':           status,
            'organization':     organization,
            'twitter_user_id':  twitter_user_id,
            'twitter_handle':   organization_twitter_handle,
        }
        return results

    twitter_user_found = False
    if positive_value_exists(twitter_user_id):
        status += "ORGANIZATION_TWITTER_DETAILS-REACHING_OUT_TO_TWITTER-BY_USER_ID "
        results = retrieve_twitter_user_info(twitter_user_id)
        if results['success']:
            twitter_user_found = True
    if not twitter_user_found and positive_value_exists(organization.organization_twitter_handle):
        status += "ORGANIZATION_TWITTER_DETAILS-REACHING_OUT_TO_TWITTER-BY_HANDLE "
        # organization_twitter_handle = organization.organization_twitter_handle
        twitter_user_id_zero = 0
        results = retrieve_twitter_user_info(twitter_user_id_zero, organization.organization_twitter_handle)
        if results['success']:
            twitter_user_found = True

    if twitter_user_found:
        status += "ORGANIZATION_TWITTER_DETAILS_RETRIEVED_FROM_TWITTER "
        twitter_user_id = results['twitter_user_id']

        # Get original image url for cache original size image
        twitter_profile_image_url_https = we_vote_image_manager.twitter_profile_image_url_https_original(
            results['twitter_json']['profile_image_url_https'])
        twitter_profile_background_image_url_https = results['twitter_json']['profile_background_image_url_https'] \
            if 'profile_background_image_url_https' in results['twitter_json'] else None
        twitter_profile_banner_url_https = results['twitter_json']['profile_banner_url'] \
            if 'profile_banner_url' in results['twitter_json'] else None
        # Cache original and resized images
        cache_results = cache_master_and_resized_image(
            organization_id=organization.id, organization_we_vote_id=organization.we_vote_id,
            twitter_id=organization.twitter_user_id,
            twitter_screen_name=organization.organization_twitter_handle,
            twitter_profile_image_url_https=twitter_profile_image_url_https,
            twitter_profile_background_image_url_https=twitter_profile_background_image_url_https,
            twitter_profile_banner_url_https=twitter_profile_banner_url_https, image_source=TWITTER)
        cached_twitter_profile_image_url_https = cache_results['cached_twitter_profile_image_url_https']
        cached_twitter_profile_background_image_url_https = \
            cache_results['cached_twitter_profile_background_image_url_https']
        cached_twitter_profile_banner_url_https = cache_results['cached_twitter_profile_banner_url_https']
        we_vote_hosted_profile_image_url_large = cache_results['we_vote_hosted_profile_image_url_large']
        we_vote_hosted_profile_image_url_medium = cache_results['we_vote_hosted_profile_image_url_medium']
        we_vote_hosted_profile_image_url_tiny = cache_results['we_vote_hosted_profile_image_url_tiny']

        # If we didn't just generate image urls for tiny, medium or large, we want to retrieve them from the image
        # cache so we can store them in the organization table below in update_organization_twitter_details
        # NOTE: In the future, we may only want to update the organization with these photos if there isn't
        # already a we_vote_hosted_profile_image already stored in the organization.
        # For now, we overwrite with a resized We Vote image if we have one
        if not positive_value_exists(we_vote_hosted_profile_image_url_tiny) or \
                not positive_value_exists(we_vote_hosted_profile_image_url_medium) or \
                not positive_value_exists(we_vote_hosted_profile_image_url_large):
            # TODO ANISHA Consider adding an option to only retrieve active images from
            # the function retrieve_we_vote_image_list_from_we_vote_id (That is, if a "retrieve_active_only"
            # setting is passed into the function, then don't return images that are active=False)
            voter_we_vote_id = None
            candidate_we_vote_id = None
            image_results = we_vote_image_manager.retrieve_we_vote_image_list_from_we_vote_id(
                voter_we_vote_id, candidate_we_vote_id, organization.we_vote_id)
            if image_results['we_vote_image_list_found']:
                we_vote_image_list = image_results['we_vote_image_list']
                for one_image in we_vote_image_list:
                    # For now we aren't checking to see if the image is marked active or not
                    # TODO ANISHA The we_vote_image_url is always coming back empty
                    if not positive_value_exists(we_vote_hosted_profile_image_url_tiny):
                        if one_image.kind_of_image_tiny:
                            we_vote_hosted_profile_image_url_tiny = one_image.we_vote_image_url
                    if not positive_value_exists(we_vote_hosted_profile_image_url_medium):
                        if one_image.kind_of_image_medium:
                            we_vote_hosted_profile_image_url_tiny = one_image.we_vote_image_url
                    if not positive_value_exists(we_vote_hosted_profile_image_url_large):
                        if one_image.kind_of_image_large:
                            we_vote_hosted_profile_image_url_large = one_image.we_vote_image_url

        save_organization_results = organization_manager.update_organization_twitter_details(
            organization, results['twitter_json'], cached_twitter_profile_image_url_https,
            cached_twitter_profile_background_image_url_https, cached_twitter_profile_banner_url_https,
            we_vote_hosted_profile_image_url_large, we_vote_hosted_profile_image_url_medium,
            we_vote_hosted_profile_image_url_tiny)
        if save_organization_results['success']:
            status += "ORGANIZATION_TWITTER_DETAILS_RETRIEVED_FROM_TWITTER_AND_SAVED "

            # Now update the Twitter statistics information in other We Vote tables
            organization = save_organization_results['organization']
            save_voter_guide_from_organization_results = update_social_media_statistics_in_other_tables(
                organization)

            # Make sure we have a TwitterUser
            save_twitter_user_results = twitter_user_manager.update_or_create_twitter_user(
                results['twitter_json'], organization.twitter_user_id, cached_twitter_profile_image_url_https,
                cached_twitter_profile_background_image_url_https, cached_twitter_profile_banner_url_https,
                we_vote_hosted_profile_image_url_large, we_vote_hosted_profile_image_url_medium,
                we_vote_hosted_profile_image_url_tiny)

            # If there is a voter with this Twitter id, then update the voter information in other tables
            save_voter_twitter_details_results = voter_manager.update_voter_twitter_details(
                organization.twitter_user_id, results['twitter_json'], cached_twitter_profile_image_url_https,
                we_vote_hosted_profile_image_url_large, we_vote_hosted_profile_image_url_medium,
                we_vote_hosted_profile_image_url_tiny)
            if save_voter_twitter_details_results['success']:
                save_position_from_voter_results = update_position_for_friends_details_from_voter(
                    save_voter_twitter_details_results['voter'])
            save_position_from_organization_results = update_position_entered_details_from_organization(
                organization)

    else:
        status += "ORGANIZATION_TWITTER_DETAILS-CLEARING_DETAILS "
        save_organization_results = organization_manager.clear_organization_twitter_details(organization)

        if save_organization_results['success']:
            results = update_social_media_statistics_in_other_tables(organization)
            status += "ORGANIZATION_TWITTER_DETAILS_CLEARED_FROM_DB "

    results = {
        'success':          True,
        'status':           status,
        'organization':     organization,
        'twitter_user_id':  twitter_user_id,
        'twitter_handle':   organization_twitter_handle,
    }
    return results


def scrape_social_media_from_one_site(site_url, retrieve_list=False):
    twitter_handle = ''
    twitter_handle_found = False
    twitter_handle_list = []
    facebook_page = ''
    facebook_page_found = False
    success = False
    if len(site_url) < 10:
        status = 'PROPER_URL_NOT_PROVIDED: ' + site_url
        results = {
            'status':               status,
            'success':              success,
            'twitter_handle':       twitter_handle,
            'twitter_handle_found': twitter_handle_found,
            'facebook_page':        facebook_page,
            'facebook_page_found':  facebook_page_found,
        }
        return results

    urllib._urlopener = FakeFirefoxURLopener()
    headers = {
        'User-Agent':
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11',
           }
    # 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    # 'Accept-Encoding': 'none',
    # 'Accept-Language': 'en-US,en;q=0.8',
    # 'Connection': 'keep-alive'
    # 'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.3',
    try:
        request = urllib.request.Request(site_url, None, headers)
        page = urllib.request.urlopen(request, timeout=5)
        for line in page.readlines():
            try:
                proceed = positive_value_exists(retrieve_list) or not twitter_handle_found
                if proceed:
                    for m in re.finditer(RE_TWITTER, line.decode()):
                        if m:
                            name = m.group(1)
                            if name not in TWITTER_BLACKLIST:
                                twitter_handle = name
                                twitter_handle_found = True
                                twitter_handle_list.append(twitter_handle)
                                if not positive_value_exists(retrieve_list):
                                    raise GetOutOfLoopLocal
            except GetOutOfLoopLocal:
                pass
            # SEE NOTE ABOUT FACEBOOK SCRAPING ABOVE
            # try:
            #     if not facebook_page_found:
            #         for m2 in re.finditer(RE_FACEBOOK, line.decode()):
            #             if m2:
            #                 possible_page1 = m2.group(1)
            #                 if possible_page1 not in FACEBOOK_BLACKLIST:
            #                     facebook_page = possible_page1
            #                     facebook_page_found = True
            #                     raise GetOutOfLoopLocal
            #                 try:
            #                     possible_page2 = m2.group(2)
            #                     if possible_page2 not in FACEBOOK_BLACKLIST:
            #                         facebook_page = possible_page2
            #                         facebook_page_found = True
            #                         raise GetOutOfLoopLocal
            #                     # ATTEMPT 1
            #                     # start_of_close_tag_index = possible_page2.find('"')
            #                     # possible_page2 = possible_page2[:start_of_close_tag_index]
            #                     # ATTEMPT 2
            #                     # fb_re = re.compile(r'facebook.com([^"]+)')
            #                     # results = fb_re.findall(possible_page2)
            #                 except Exception as error_instance:
            #                     pass
            #                 # possible_page3 = m2.group(3)
            #                 # possible_page4 = m2.group(4)
            # except GetOutOfLoopLocal:
            #     pass
            if twitter_handle_found and not positive_value_exists(retrieve_list):  # and facebook_page_found:
                raise GetOutOfLoop
        success = True
        status = 'FINISHED_SCRAPING_PAGE'
    except timeout:
        status = "SCRAPE_TIMEOUT_ERROR"
        success = False
    except GetOutOfLoop:
        success = True
        status = 'TWITTER_HANDLE_FOUND-BREAK_OUT'
    except IOError as error_instance:
        # Catch the error message coming back from urllib.request.urlopen and pass it in the status
        error_message = error_instance
        status = "SCRAPE_SOCIAL_IO_ERROR: {error_message}".format(error_message=error_message)
        success = False
    except Exception as error_instance:
        error_message = error_instance
        status = "SCRAPE_GENERAL_EXCEPTION_ERROR: {error_message}".format(error_message=error_message)
        success = False

    results = {
        'status':               status,
        'success':              success,
        'page_redirected':      twitter_handle,
        'twitter_handle':       twitter_handle,
        'twitter_handle_list':  twitter_handle_list,
        'twitter_handle_found': twitter_handle_found,
        'facebook_page':        facebook_page,
        'facebook_page_found':  facebook_page_found,
    }
    return results


def scrape_and_save_social_media_from_all_organizations(state_code='', force_retrieve=False):
    facebook_pages_found = 0
    twitter_handles_found = 0

    organization_manager = OrganizationManager()
    organization_list_query = Organization.objects.order_by('organization_name')
    if positive_value_exists(state_code):
        organization_list_query = organization_list_query.filter(state_served_code=state_code)

    organization_list = organization_list_query
    for organization in organization_list:
        twitter_handle = False
        facebook_page = False
        if not organization.organization_website:
            continue
        if (not positive_value_exists(organization.organization_twitter_handle)) or force_retrieve:
            scrape_results = scrape_social_media_from_one_site(organization.organization_website)

            # Only include a change if we have a new value (do not try to save blank value)
            if scrape_results['twitter_handle_found'] and positive_value_exists(scrape_results['twitter_handle']):
                twitter_handle = scrape_results['twitter_handle']
                twitter_handles_found += 1

            if scrape_results['facebook_page_found'] and positive_value_exists(scrape_results['facebook_page']):
                facebook_page = scrape_results['facebook_page']
                facebook_pages_found += 1

            save_results = organization_manager.update_organization_social_media(organization, twitter_handle,
                                                                                 facebook_page)

        # ######################################
        # We refresh the Twitter information in another function

    status = "ORGANIZATION_SOCIAL_MEDIA_SCRAPED"
    results = {
        'success':                  True,
        'status':                   status,
        'twitter_handles_found':    twitter_handles_found,
        'facebook_pages_found':     facebook_pages_found,
    }
    return results


def refresh_twitter_data_for_organizations(state_code='', google_civic_election_id=0, first_retrieve_only=False):
    status = ""
    number_of_twitter_accounts_queried = 0
    number_of_organizations_updated = 0

    organization_list_query = Organization.objects.order_by('organization_name')
    if positive_value_exists(state_code):
        organization_list_query = organization_list_query.filter(state_served_code=state_code)

    # Limit this to organizations that have a voter guide in a particular election
    if positive_value_exists(google_civic_election_id):
        voter_guide_list_manager = VoterGuideListManager()
        results = voter_guide_list_manager.retrieve_voter_guides_for_election(google_civic_election_id)
        if results['voter_guide_list_found']:
            organization_we_vote_ids_in_this_election = []
            voter_guide_list = results['voter_guide_list']
            for one_voter_guide in voter_guide_list:
                if positive_value_exists(one_voter_guide.organization_we_vote_id):
                    organization_we_vote_ids_in_this_election.append(one_voter_guide.organization_we_vote_id)
            # Only return the organizations with a voter guide for this election
            organization_list_query = organization_list_query.filter(
                we_vote_id__in=organization_we_vote_ids_in_this_election)
        else:
            status += "NO_VOTER_GUIDES_FOUND_FOR_THIS_ELECTION "
            results = {
                'success': False,
                'status': status,
                'number_of_twitter_accounts_queried': number_of_twitter_accounts_queried,
                'number_of_organizations_updated': number_of_organizations_updated,
            }
            return results

    organization_list = list(organization_list_query)

    twitter_user_manager = TwitterUserManager()
    for organization in organization_list:
        # ######################################
        # Do we have a TwitterLinkToOrganization for this org?
        twitter_user_id_found = False
        twitter_id = 0
        results = twitter_user_manager.retrieve_twitter_link_to_organization_from_organization_we_vote_id(
            organization.we_vote_id)
        if results['twitter_link_to_organization_found']:
            twitter_link_to_organization = results['twitter_link_to_organization']
            twitter_id = twitter_link_to_organization.twitter_id
            twitter_user_id_found = True

        # If we can find a twitter_id from the TwitterLinkToOrganization table, we want to use that
        if twitter_user_id_found or organization.organization_twitter_handle:
            retrieved_twitter_data = False
            if positive_value_exists(first_retrieve_only):
                if not positive_value_exists(organization.twitter_followers_count):
                    refresh_results = refresh_twitter_organization_details(organization, twitter_id)
                    # twitter_user_id = 0
                    # results = retrieve_twitter_user_info(twitter_user_id, organization.organization_twitter_handle)
                    retrieved_twitter_data = refresh_results['success']
                    organization = refresh_results['organization']
                    number_of_twitter_accounts_queried += 1
            else:
                refresh_results = refresh_twitter_organization_details(organization, twitter_id)
                # twitter_user_id = 0
                # results = retrieve_twitter_user_info(twitter_user_id, organization.organization_twitter_handle)
                retrieved_twitter_data = refresh_results['success']
                organization = refresh_results['organization']
                number_of_twitter_accounts_queried += 1

            if retrieved_twitter_data:
                number_of_organizations_updated += 1
                # save_results = organization_manager.update_organization_twitter_details(
                #     organization, results['twitter_json'])

                # if save_results['success']:
                update_results = update_social_media_statistics_in_other_tables(organization)

    status = "ALL_ORGANIZATION_TWITTER_DATA_RETRIEVED"
    results = {
        'success':                              True,
        'status':                               status,
        'number_of_twitter_accounts_queried':   number_of_twitter_accounts_queried,
        'number_of_organizations_updated':      number_of_organizations_updated,
    }
    return results


def scrape_and_save_social_media_for_candidates_in_one_election(google_civic_election_id=0, state_code=''):
    facebook_pages_found = 0
    twitter_handles_found = 0
    force_retrieve = False
    status = ""
    google_civic_election_id = convert_to_int(google_civic_election_id)

    candidate_manager = CandidateCampaignManager()
    candidate_list_manager = CandidateCampaignListManager()
    return_list_of_objects = True
    results = candidate_list_manager.retrieve_all_candidates_for_upcoming_election(google_civic_election_id, state_code,
                                                                                   return_list_of_objects)
    status += results['status']
    if results['success']:
        candidate_list = results['candidate_list_objects']
    else:
        candidate_list = []

    for candidate in candidate_list:
        twitter_handle = False
        facebook_page = False
        if not candidate.candidate_url:
            continue
        if (not positive_value_exists(candidate.candidate_twitter_handle)) or force_retrieve:
            scrape_results = scrape_social_media_from_one_site(candidate.candidate_url)

            # Only include a change if we have a new value (do not try to save blank value)
            if scrape_results['twitter_handle_found'] and positive_value_exists(scrape_results['twitter_handle']):
                twitter_handle = scrape_results['twitter_handle']
                twitter_handles_found += 1

            if scrape_results['facebook_page_found'] and positive_value_exists(scrape_results['facebook_page']):
                facebook_page = scrape_results['facebook_page']
                facebook_pages_found += 1

            save_results = candidate_manager.update_candidate_social_media(candidate, twitter_handle, facebook_page)

        # ######################################
        # We refresh the Twitter information in another function

    status = "ORGANIZATION_SOCIAL_MEDIA_RETRIEVED"
    results = {
        'success':                  True,
        'status':                   status,
        'twitter_handles_found':    twitter_handles_found,
        'facebook_pages_found':     facebook_pages_found,
    }
    return results


def refresh_twitter_candidate_details_for_election(google_civic_election_id, state_code):
    twitter_handles_added = 0
    profiles_refreshed_with_twitter_data = 0

    google_civic_election_id = convert_to_int(google_civic_election_id)

    candidate_list_manager = CandidateCampaignListManager()
    return_list_of_objects = True
    candidates_results = candidate_list_manager.retrieve_all_candidates_for_upcoming_election(
        google_civic_election_id, state_code, return_list_of_objects)
    if candidates_results['candidate_list_found']:
        candidate_list = candidates_results['candidate_list_objects']

        for candidate in candidate_list:
            # Extract twitter_handle from google_civic_election information
            if positive_value_exists(candidate.twitter_url) \
                    and not positive_value_exists(candidate.candidate_twitter_handle):
                # If we got a twitter_url from Google Civic, and we haven't already stored a twitter handle, move it
                candidate.candidate_twitter_handle = extract_twitter_handle_from_text_string(candidate.twitter_url)
                candidate.save()
                twitter_handles_added += 1
            if positive_value_exists(candidate.candidate_twitter_handle):
                refresh_twitter_candidate_details(candidate)
                profiles_refreshed_with_twitter_data += 1
                refresh_candidate_results = refresh_candidate_data_from_master_tables(candidate.we_vote_id)

    status = "CANDIDATE_SOCIAL_MEDIA_RETRIEVED"
    results = {
        'success':                              True,
        'status':                               status,
        'twitter_handles_added':                twitter_handles_added,
        'profiles_refreshed_with_twitter_data': profiles_refreshed_with_twitter_data,
    }
    return results


def transfer_candidate_twitter_handles_from_google_civic(google_civic_election_id=0, state_code=''):
    twitter_handles_transferred = 0
    status = ""
    google_civic_election_id = convert_to_int(google_civic_election_id)

    candidate_list_object = CandidateCampaignListManager()
    return_list_of_objects = True
    results = candidate_list_object.retrieve_all_candidates_for_upcoming_election(google_civic_election_id,
                                                                                  state_code,
                                                                                  return_list_of_objects)
    status += results['status']
    if results['success']:
        candidate_list = results['candidate_list_objects']
    else:
        candidate_list = []

    for candidate in candidate_list:
        if not candidate.twitter_url:
            continue
        # Only proceed if we don't already have a twitter_handle
        if not positive_value_exists(candidate.candidate_twitter_handle):
            candidate.candidate_twitter_handle = candidate.twitter_url.replace("https://twitter.com/", "")
            candidate.save()
            twitter_handles_transferred += 1

        # ######################################
        # We refresh the Twitter information in another function

    status += " CANDIDATE_TWITTER_HANDLES_TRANSFERRED"
    results = {
        'success':                      True,
        'status':                       status,
        'twitter_handles_transferred':  twitter_handles_transferred,
    }
    return results


def twitter_sign_in_start_for_api(voter_device_id, return_url, cordova):  # twitterSignInStart
    """

    :param voter_device_id:
    :param return_url: Where to direct the browser at the very end of the process
    :param cordova:
    :return:
    """
    # Get voter_id from the voter_device_id
    results = is_voter_device_id_valid(voter_device_id)
    if not results['success']:
        results = {
            'success':                      False,
            'status':                       "VALID_VOTER_DEVICE_ID_MISSING",
            'voter_device_id':              voter_device_id,
            'twitter_redirect_url':         '',
            'voter_info_retrieved':         False,
            'switch_accounts':              False,
            'jump_to_request_voter_info':   False,
            'return_url':                   return_url,
        }
        return results

    voter_manager = VoterManager()
    results = voter_manager.retrieve_voter_from_voter_device_id(voter_device_id)
    if not positive_value_exists(results['voter_found']):
        results = {
            'status':                       "VALID_VOTER_MISSING",
            'success':                      False,
            'voter_device_id':              voter_device_id,
            'twitter_redirect_url':         '',
            'voter_info_retrieved':         False,
            'switch_accounts':              False,
            'jump_to_request_voter_info':   False,
            'return_url':                   return_url,
        }
        return results

    voter = results['voter']

    twitter_user_manager = TwitterUserManager()
    twitter_user_results = twitter_user_manager.retrieve_twitter_link_to_voter(voter.we_vote_id)
    if twitter_user_results['twitter_link_to_voter_found']:
        error_results = {
            'status':                       "TWITTER_OWNER_VOTER_FOUND_WHEN_NOT_EXPECTED",
            'success':                      False,
            'voter_device_id':              voter_device_id,
            'twitter_redirect_url':         '',
            'voter_info_retrieved':         False,
            'switch_accounts':              False,  # If true, new voter_device_id returned
            'jump_to_request_voter_info':   False,
            'return_url':                   return_url,
        }
        return error_results

    twitter_auth_manager = TwitterAuthManager()
    auth_response_results = twitter_auth_manager.retrieve_twitter_auth_response(voter_device_id)
    if auth_response_results['twitter_auth_response_found']:
        twitter_auth_response = auth_response_results['twitter_auth_response']
    else:
        # Create a new twitter_auth_response entry with only the voter_device_id
        auth_create_results = twitter_auth_manager.update_or_create_twitter_auth_response(voter_device_id)

        if not auth_create_results['twitter_auth_response_created']:
            error_results = {
                'status':                       auth_create_results['status'],
                'success':                      False,
                'voter_device_id':              voter_device_id,
                'twitter_redirect_url':         '',
                'voter_info_retrieved':         False,
                'switch_accounts':              False,  # If true, new voter_device_id returned
                'jump_to_request_voter_info':   False,
                'return_url':                   return_url,
            }
            return error_results

        twitter_auth_response = auth_create_results['twitter_auth_response']

    # ### This whole block causes a "No 'Access-Control-Allow-Origin'" error:
    #   XMLHttpRequest cannot load http://localhost:3000/twitter_sign_in. No 'Access-Control-Allow-Origin' header is
    #   present on the requested resource. Origin 'null' is therefore not allowed access.
    # I think it is good to ask them to authenticate again
    # if twitter_auth_response.twitter_access_token and twitter_auth_response.twitter_access_secret:
    #     # If here the voter might already be signed in, so we don't want to ask them to approve again
    #     auth = tweepy.OAuthHandler(TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET)
    #     auth.set_access_token(twitter_auth_response.twitter_access_token, twitter_auth_response.twitter_access_secret)
    #
    #     api = tweepy.API(auth)
    #
    #     try:
    #         tweepy_user_object = api.me()
    #         success = True
    #     # What is the error situation where the twitter_access_token and twitter_access_secret are no longer valid?
    #     # We need to deal with this (wipe them from the database and rewind to the right place in the process
    #     except tweepy.RateLimitError:
    #         success = False
    #         status = 'TWITTER_RATE_LIMIT_ERROR'
    #     except tweepy.error.TweepError as error_instance:
    #         success = False
    #         status = error_instance.reason
    #
    #     if success:
    #         # Reach out to the twitterSignInRequestVoterInfo -- no need to redirect
    #         empty_return_url = ""  # We set this to empty so we get a response instead of a redirection
    #         voter_info_results = twitter_sign_in_request_voter_info_for_api(voter_device_id, empty_return_url)
    #
    #         success = voter_info_results['success']
    #         status = "SKIPPED_AUTH_DIRECT_REQUEST_VOTER_INFO: " + voter_info_results['status'] + " "
    #         results = {
    #             'status':                       status,
    #             'success':                      success,
    #             'voter_device_id':              voter_device_id,
    #             'twitter_redirect_url':         '',
    #             'voter_info_retrieved':         voter_info_results['voter_info_retrieved'],
    #             'switch_accounts':              voter_info_results['switch_accounts'],
    #             'jump_to_request_voter_info':   True,
    #             'return_url':                   return_url,
    #         }
    #         return results
    #     else:
    #         # Somehow reset tokens and start over.
    #         pass

    callback_url = WE_VOTE_SERVER_ROOT_URL + "/apis/v1/twitterSignInRequestAccessToken/"
    callback_url += "?voter_device_id=" + voter_device_id
    callback_url += "&return_url=" + return_url
    callback_url += "&cordova=" + str(cordova)

    try:
        # We take the Consumer Key and the Consumer Secret, and request a token & token_secret
        auth = tweepy.OAuthHandler(TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET, callback_url)
        twitter_authorization_url = auth.get_authorization_url()
        request_token_dict = auth.request_token
        twitter_request_token = ''
        twitter_request_token_secret = ''

        if 'oauth_token' in request_token_dict:
            twitter_request_token = request_token_dict['oauth_token']
        if 'oauth_token_secret' in request_token_dict:
            twitter_request_token_secret = request_token_dict['oauth_token_secret']

        # We save these values in the TwitterAuthResponse table, and then return a twitter_authorization_url
        # where the voter signs in
        # Once they sign in to the Twitter login, they are redirected back to the We Vote callback_url
        # On that callback_url page, we are told if they are signed in
        #  on Twitter or not, and capture an access key we can use to retrieve information about the Twitter user
        # NOTE: Regarding the callback url, I think this can just be a direct call to the API server,
        #  since we have the voter_device_id
        if positive_value_exists(twitter_request_token) and positive_value_exists(twitter_request_token_secret):
            twitter_auth_response.twitter_request_token = twitter_request_token
            twitter_auth_response.twitter_request_secret = twitter_request_token_secret
            twitter_auth_response.save()

            success = True
            status = "TWITTER_REDIRECT_URL_RETRIEVED"
        else:
            success = False
            status = "TWITTER_REDIRECT_URL_NOT_RETRIEVED"

    except tweepy.RateLimitError:
        success = False
        status = 'TWITTER_RATE_LIMIT_ERROR'
    except tweepy.error.TweepError as error_instance:
        success = False
        status = 'TWITTER_SIGN_IN_START: {}'.format(error_instance.reason)

    if success:
        results = {
            'status':                       status,
            'success':                      True,
            'voter_device_id':              voter_device_id,
            'twitter_redirect_url':         twitter_authorization_url,
            'voter_info_retrieved':         False,
            'switch_accounts':              False,
            'jump_to_request_voter_info':   False,
            'return_url':                   return_url,
        }
    else:
        results = {
            'status':                       status,
            'success':                      False,
            'voter_device_id':              voter_device_id,
            'twitter_redirect_url':         '',
            'voter_info_retrieved':         False,
            'switch_accounts':              False,
            'jump_to_request_voter_info':   False,
            'return_url':                   return_url,
        }
    return results

def twitter_native_sign_in_save_for_api(voter_device_id, twitter_access_token, twitter_access_secret):
    """
    For react-native-oauth, we receive the tokens from a single authenticate() call, and save them to the
    TwitterAuthManager().  This is equivalent to Steps 1 & 2 in the WebApp oAuth processing

    :param voter_device_id:
    :param twitter_access_token:  react-native-oauth refers to this as the "access_token"
    :param twitter_access_secret: react-native-oauth refers to this as the "access_token_secret"
    :return:
    """
    # Get voter_id from the voter_device_id
    results = is_voter_device_id_valid(voter_device_id)
    if not results['success']:
        results = {
            'success':                      False,
            'status':                       "VALID_VOTER_DEVICE_ID_MISSING",
            'voter_device_id':              voter_device_id,
        }
        return results

    voter_manager = VoterManager()
    results = voter_manager.retrieve_voter_from_voter_device_id(voter_device_id)
    if not positive_value_exists(results['voter_found']):
        results = {
            'status':                       "VALID_VOTER_MISSING",
            'success':                      False,
            'voter_device_id':              voter_device_id,
        }
        return results

    voter = results['voter']

    twitter_user_manager = TwitterUserManager()
    twitter_user_results = twitter_user_manager.retrieve_twitter_link_to_voter(voter.we_vote_id)
    if twitter_user_results['twitter_link_to_voter_found']:
        error_results = {
            'status':                       "TWITTER_OWNER_VOTER_FOUND_WHEN_NOT_EXPECTED",
            'success':                      False,
            'voter_device_id':              voter_device_id,
         }
        return error_results

    twitter_auth_manager = TwitterAuthManager()
    auth_response_results = twitter_auth_manager.retrieve_twitter_auth_response(voter_device_id)
    if auth_response_results['twitter_auth_response_found']:
        twitter_auth_response = auth_response_results['twitter_auth_response']
    else:
        # Create a new twitter_auth_response entry with only the voter_device_id
        auth_create_results = twitter_auth_manager.update_or_create_twitter_auth_response(voter_device_id)

        if not auth_create_results['twitter_auth_response_created']:
            error_results = {
                'status':                       auth_create_results['status'],
                'success':                      False,
                'voter_device_id':              voter_device_id,
            }
            return error_results

        twitter_auth_response = auth_create_results['twitter_auth_response']

    try:
        if positive_value_exists(twitter_access_token) and positive_value_exists(twitter_access_secret):
            twitter_auth_response.twitter_access_token = twitter_access_token
            twitter_auth_response.twitter_access_secret = twitter_access_secret
            twitter_auth_response.twitter_request_token = TWITTER_NATIVE_INDICATOR
            twitter_auth_response.twitter_request_secret = TWITTER_NATIVE_INDICATOR
            twitter_auth_response.save()

            success = True
            status = 'TWITTER_TOKENS_STORED'
        else:
            success = False
            status = 'TWITTER_TOKENS_NOT_STORED_DUE_TO_BAD_PASSED_IN_TOKENS'
            logger.error('twitter_native_sign_in_save_for_api -- TWITTER_TOKENS_NOT_STORED_BAD_PASSED_IN_TOKENS')

    except Exception as e:
        success = False
        status = 'TWITTER_TOKEN_EXCEPTION_ON_FAILED_SAVE'
        logger.error('twitter_native_sign_in_save_for_api -- save threw exception: ' + str(e))

    if success:
        results = {
            'status':                       status,
            'success':                      True,
            'voter_device_id':              voter_device_id,
            'voter_info_retrieved':         False,
            'switch_accounts':              False,
            'jump_to_request_voter_info':   False,
        }
    else:
        results = {
            'status':                       status,
            'success':                      False,
            'voter_device_id':              voter_device_id,
            'voter_info_retrieved':         False,
            'switch_accounts':              False,
            'jump_to_request_voter_info':   False,
        }
    return results


def twitter_sign_in_request_access_token_for_api(voter_device_id,
                                                 incoming_request_token, incoming_oauth_verifier,
                                                 return_url, cordova):
    """
    twitterSignInRequestAccessToken
    After signing in and agreeing to the application's terms, the user is redirected back to the application with
    the same request token and another value, this time the OAuth verifier.

    Within this function we use
    1) the request token and
    2) request secret along with the
    3) OAuth verifier to get an access token, also from Twitter.
    :param voter_device_id:
    :param incoming_request_token:
    :param incoming_oauth_verifier:
    :param return_url: If a value is provided, return to this URL when the whole process is complete
    :param cordova:
    :return:
    """
    # Get voter_id from the voter_device_id
    results = is_voter_device_id_valid(voter_device_id)
    if not results['success']:
        results = {
            'success':                          False,
            'status':                           "VALID_VOTER_DEVICE_ID_MISSING",
            'voter_device_id':                  voter_device_id,
            'access_token_and_secret_returned': False,
            'return_url':                       return_url,
            'cordova':                          cordova,
        }
        return results

    voter_manager = VoterManager()
    results = voter_manager.retrieve_voter_from_voter_device_id(voter_device_id)
    if not positive_value_exists(results['voter_found']):
        results = {
            'status':                           "VALID_VOTER_MISSING",
            'success':                          False,
            'voter_device_id':                  voter_device_id,
            'access_token_and_secret_returned': False,
            'return_url':                       return_url,
            'cordova':                          cordova,
        }
        return results

    voter = results['voter']

    twitter_auth_manager = TwitterAuthManager()
    auth_response_results = twitter_auth_manager.retrieve_twitter_auth_response(voter_device_id)
    if not auth_response_results['twitter_auth_response_found']:
        results = {
            'status':                           "REQUEST_ACCESS_TOKEN-TWITTER_AUTH_RESPONSE_NOT_FOUND",
            'success':                          False,
            'voter_device_id':                  voter_device_id,
            'access_token_and_secret_returned': False,
            'return_url':                       return_url,
            'cordova':                          cordova,
        }
        return results

    twitter_auth_response = auth_response_results['twitter_auth_response']

    if not twitter_auth_response.twitter_request_token == incoming_request_token:
        results = {
            'status':                           "TWITTER_REQUEST_TOKEN_DOES_NOT_MATCH_STORED_VOTER_VALUE",
            'success':                          False,
            'voter_device_id':                  voter_device_id,
            'access_token_and_secret_returned': False,
            'return_url':                       return_url,
            'cordova':                          cordova,
        }
        return results

    twitter_access_token = ''
    twitter_access_token_secret = ''
    try:
        # We take the Request Token, Request Secret, and OAuth Verifier and request an access_token
        auth = tweepy.OAuthHandler(TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET)
        auth.request_token = {'oauth_token': twitter_auth_response.twitter_request_token,
                              'oauth_token_secret': twitter_auth_response.twitter_request_secret}
        auth.get_access_token(incoming_oauth_verifier)
        if positive_value_exists(auth.access_token) and positive_value_exists(auth.access_token_secret):
            twitter_access_token = auth.access_token
            twitter_access_token_secret = auth.access_token_secret

    except tweepy.RateLimitError:
        success = False
        status = 'TWITTER_RATE_LIMIT_ERROR'
    except tweepy.error.TweepError as error_instance:
        success = False
        status = 'TWITTER_SIGN_IN_REQUEST_ACCESS_TOKEN: {}'.format(error_instance.reason)

    try:
        # We save these values in the TwitterAuthResponse table
        if positive_value_exists(twitter_access_token) and positive_value_exists(twitter_access_token_secret):
            twitter_auth_response.twitter_access_token = twitter_access_token
            twitter_auth_response.twitter_access_secret = twitter_access_token_secret
            twitter_auth_response.save()

            success = True
            status = "TWITTER_ACCESS_TOKEN_RETRIEVED_AND_SAVED"
        else:
            success = False
            status = "TWITTER_ACCESS_TOKEN_NOT_RETRIEVED"
    except Exception as e:
        success = False
        status = "TWITTER_ACCESS_TOKEN_NOT_SAVED"

    if success:
        results = {
            'status':                           status,
            'success':                          True,
            'voter_device_id':                  voter_device_id,
            'access_token_and_secret_returned': True,
            'return_url':                       return_url,
            'cordova':                          cordova,
        }
    else:
        results = {
            'status':                           status,
            'success':                          False,
            'voter_device_id':                  voter_device_id,
            'access_token_and_secret_returned': False,
            'return_url':                       return_url,
            'cordova':                          cordova,
        }
    return results


def twitter_sign_in_request_voter_info_for_api(voter_device_id, return_url):
    """
    (not directly called by) twitterSignInRequestVoterInfo
    When here, the incoming voter_device_id should already be authenticated
    :param voter_device_id:
    :param return_url: Where to return the browser when sign in process is complete
    :return:
    """

    twitter_handle = ''
    twitter_handle_found = False
    tweepy_user_object = None
    twitter_user_object_found = False
    voter_info_retrieved = False
    switch_accounts = False
    twitter_secret_key = ""

    # Get voter_id from the voter_device_id
    results = is_voter_device_id_valid(voter_device_id)
    if not results['success']:
        results = {
            'success':              False,
            'status':               "VALID_VOTER_DEVICE_ID_MISSING",
            'voter_device_id':      voter_device_id,
            'twitter_handle':       twitter_handle,
            'twitter_handle_found': twitter_handle_found,
            'voter_info_retrieved': voter_info_retrieved,
            'switch_accounts':      switch_accounts,
            'return_url':           return_url,
            'twitter_secret_key':   twitter_secret_key,
        }
        return results

    voter_manager = VoterManager()
    results = voter_manager.retrieve_voter_from_voter_device_id(voter_device_id)
    if not positive_value_exists(results['voter_found']):
        results = {
            'status':               "VALID_VOTER_MISSING",
            'success':              False,
            'voter_device_id':      voter_device_id,
            'twitter_handle':       twitter_handle,
            'twitter_handle_found': twitter_handle_found,
            'voter_info_retrieved': voter_info_retrieved,
            'switch_accounts':      switch_accounts,
            'return_url':           return_url,
            'twitter_secret_key':   twitter_secret_key,
        }
        return results

    voter = results['voter']
    voter_we_vote_id = voter.we_vote_id

    twitter_auth_manager = TwitterAuthManager()
    auth_response_results = twitter_auth_manager.retrieve_twitter_auth_response(voter_device_id)
    if not auth_response_results['twitter_auth_response_found']:
        results = {
            'status':               "TWITTER_AUTH_RESPONSE_NOT_FOUND",
            'success':              False,
            'voter_device_id':      voter_device_id,
            'twitter_handle':       twitter_handle,
            'twitter_handle_found': twitter_handle_found,
            'voter_info_retrieved': voter_info_retrieved,
            'switch_accounts':      switch_accounts,
            'return_url':           return_url,
            'twitter_secret_key':   twitter_secret_key,
        }
        return results

    twitter_auth_response = auth_response_results['twitter_auth_response']

    auth = tweepy.OAuthHandler(TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET)
    auth.set_access_token(twitter_auth_response.twitter_access_token, twitter_auth_response.twitter_access_secret)

    api = tweepy.API(auth)

    try:
        tweepy_user_object = api.me()
        twitter_json = tweepy_user_object._json

        success = True
        status = 'TWITTER_SIGN_IN_REQUEST_VOTER_INFO_SUCCESSFUL '
        twitter_handle = tweepy_user_object.screen_name
        twitter_handle_found = True
        twitter_user_object_found = True
    except tweepy.RateLimitError:
        success = False
        status = 'TWITTER_SIGN_IN_REQUEST_VOTER_INFO_RATE_LIMIT_ERROR '
    except tweepy.error.TweepError as error_instance:
        success = False
        status = 'TWITTER_SIGN_IN_REQUEST_VOTER_INFO_TWEEPY_ERROR: {}'.format(error_instance.reason)

    if twitter_user_object_found:
        status += "TWITTER_SIGN_IN-ALREADY_LINKED_TO_OTHER_ACCOUNT "
        success = True
        save_user_results = twitter_auth_manager.save_twitter_auth_values(twitter_auth_response, tweepy_user_object)

        if save_user_results['success']:
            voter_info_retrieved = True
        status += save_user_results['status']

    twitter_user_manager = TwitterUserManager()
    twitter_link_to_voter_results = twitter_user_manager.retrieve_twitter_link_to_voter_from_voter_we_vote_id(
        voter_we_vote_id)
    if twitter_link_to_voter_results['twitter_link_to_voter_found']:
        twitter_link_to_voter = twitter_link_to_voter_results['twitter_link_to_voter']
        twitter_secret_key = twitter_link_to_voter.secret_key

    results = {
        'status':               status,
        'success':              success,
        'voter_device_id':      voter_device_id,
        'twitter_handle':       twitter_handle,
        'twitter_handle_found': twitter_handle_found,
        'voter_info_retrieved': voter_info_retrieved,
        'switch_accounts':      switch_accounts,
        'return_url':           return_url,
        'twitter_secret_key':   twitter_secret_key,
    }
    return results


def twitter_sign_in_retrieve_for_api(voter_device_id):  # twitterSignInRetrieve
    """
    We are asking for the results of the most recent Twitter authentication

    July 2017: We want the TwitterUser class/table to be the authoritative source of twitter info, ideally
    TwitterUser feeds the duplicated columns in voter, organization, candidate, etc.
    Unfortunately Django Auth, pre-populates voter with some key info first, which is fine, but makes it less clean.

    :param voter_device_id:
    :return:
    """
    voter_manager = VoterManager()
    voter_results = voter_manager.retrieve_voter_from_voter_device_id(voter_device_id)
    voter_id = voter_results['voter_id']
    if not positive_value_exists(voter_id):
        success = False
        error_results = {
            'success':                                  success,
            'status':                                   "TWITTER_SIGN_IN_NO_VOTER",
            'voter_device_id':                          voter_device_id,
            'voter_we_vote_id':                         "",
            'voter_has_data_to_preserve':               False,
            'existing_twitter_account_found':           False,
            'voter_we_vote_id_attached_to_twitter':     "",
            'twitter_sign_in_found':                    False,
            'twitter_sign_in_verified':                 False,
            'twitter_sign_in_failed':                   True,
            'twitter_secret_key':                       "",
            'twitter_access_secret':                    "",
            'twitter_access_token':                     "",
            'twitter_id':                               0,
            'twitter_name':                             "",
            'twitter_profile_image_url_https':          "",
            'twitter_request_secret':                   "",
            'twitter_request_token':                    "",
            'twitter_screen_name':                      "",
            'we_vote_hosted_profile_image_url_large':   "",
            'we_vote_hosted_profile_image_url_medium':  "",
            'we_vote_hosted_profile_image_url_tiny':    "",
        }
        return error_results
    voter = voter_results['voter']
    voter_we_vote_id = voter.we_vote_id
    voter_has_data_to_preserve = voter.has_data_to_preserve()

    twitter_auth_manager = TwitterAuthManager()
    auth_response_results = twitter_auth_manager.retrieve_twitter_auth_response(voter_device_id)
    status = auth_response_results['status']
    if not auth_response_results['twitter_auth_response_found']:
        success = False
        error_results = {
            'success':                                  success,
            'status':                                   status,
            'voter_device_id':                          voter_device_id,
            'voter_we_vote_id':                         voter_we_vote_id,
            'voter_has_data_to_preserve':               False,
            'existing_twitter_account_found':           False,
            'voter_we_vote_id_attached_to_twitter':     "",
            'twitter_sign_in_found':                    False,
            'twitter_sign_in_verified':                 False,
            'twitter_sign_in_failed':                   True,
            'twitter_secret_key':                       "",
            'twitter_access_secret':                    "",
            'twitter_access_token':                     "",
            'twitter_id':                               0,
            'twitter_name':                             "",
            'twitter_profile_image_url_https':          "",
            'twitter_request_secret':                   "",
            'twitter_request_token':                    "",
            'twitter_screen_name':                      "",
            'we_vote_hosted_profile_image_url_large':   "",
            'we_vote_hosted_profile_image_url_medium':  "",
            'we_vote_hosted_profile_image_url_tiny':    "",
        }
        return error_results

    success = True
    twitter_auth_response = auth_response_results['twitter_auth_response']
    twitter_id = twitter_auth_response.twitter_id

    if not twitter_id:
        success = False
        error_results = {
            'success':                                  success,
            'status':                                   status,
            'voter_device_id':                          voter_device_id,
            'voter_we_vote_id':                         voter_we_vote_id,
            'voter_has_data_to_preserve':               False,
            'existing_twitter_account_found':           False,
            'voter_we_vote_id_attached_to_twitter':     "",
            'twitter_sign_in_found':                    False,
            'twitter_sign_in_verified':                 False,
            'twitter_sign_in_failed':                   True,
            'twitter_secret_key':                       "",
            'twitter_access_secret':                    "",
            'twitter_access_token':                     "",
            'twitter_id':                               0,
            'twitter_name':                             "",
            'twitter_profile_image_url_https':          "",
            'twitter_request_secret':                   "",
            'twitter_request_token':                    "",
            'twitter_screen_name':                      "",
            'we_vote_hosted_profile_image_url_large':   "",
            'we_vote_hosted_profile_image_url_medium':  "",
            'we_vote_hosted_profile_image_url_tiny':    "",
        }
        return error_results

    twitter_user_manager = TwitterUserManager()
    twitter_sign_in_verified = True
    twitter_sign_in_failed = False
    twitter_secret_key = ""
    existing_twitter_account_found = False
    voter_we_vote_id_attached_to_twitter = ""
    repair_twitter_related_voter_caching_now = False

    twitter_link_results = twitter_user_manager.retrieve_twitter_link_to_voter(twitter_id)
    if twitter_link_results['twitter_link_to_voter_found']:
        twitter_link_to_voter = twitter_link_results['twitter_link_to_voter']
        status += " " + twitter_link_results['status']
        voter_we_vote_id_attached_to_twitter = twitter_link_to_voter.voter_we_vote_id
        twitter_secret_key = twitter_link_to_voter.secret_key
        existing_twitter_account_found = True
        repair_twitter_related_voter_caching_now = True
    else:
        # Look in the voter table for any records with a twitter_id and link to the first one
        voter_results = voter_manager.retrieve_voter_by_twitter_id_old(twitter_id)
        if voter_results['voter_found']:
            voter_with_twitter_id = voter_results['voter']
            voter_we_vote_id_attached_to_twitter = voter_with_twitter_id.we_vote_id
            if positive_value_exists(voter_we_vote_id_attached_to_twitter):
                save_results = twitter_user_manager.create_twitter_link_to_voter(
                    twitter_id, voter_we_vote_id_attached_to_twitter)
                status += " " + save_results['status']
                if save_results['success']:
                    repair_twitter_related_voter_caching_now = True

    if twitter_id:
        # We do this here as part of the Twitter sign in process, to make sure we don't have multiple organizations
        #  using the same twitter_id (once there is a TwitterLinkToOrganization).
        organization_list_manager = OrganizationListManager()
        repair_results = organization_list_manager.repair_twitter_related_organization_caching(
            twitter_id)
        status += repair_results['status']
        if repair_twitter_related_voter_caching_now:
            # And make sure we don't have multiple voters using same twitter_id (once there is a TwitterLinkToVoter)
            repair_results = voter_manager.repair_twitter_related_voter_caching(
                twitter_id)
            status += repair_results['status']

    if positive_value_exists(voter_we_vote_id_attached_to_twitter):
        voter_we_vote_id_for_cache = voter_we_vote_id_attached_to_twitter
    else:
        voter_we_vote_id_for_cache = voter_we_vote_id
    # Cache original and resized images
    cache_results = cache_master_and_resized_image(
        voter_we_vote_id=voter_we_vote_id_for_cache,
        twitter_id=twitter_id, twitter_screen_name=twitter_auth_response.twitter_screen_name,
        twitter_profile_image_url_https=twitter_auth_response.twitter_profile_image_url_https,
        twitter_profile_banner_url_https=twitter_auth_response.twitter_profile_banner_url_https,
        image_source=TWITTER)
    cached_twitter_profile_image_url_https = cache_results['cached_twitter_profile_image_url_https']
    cached_twitter_profile_banner_url_https = cache_results['cached_twitter_profile_banner_url_https']
    we_vote_hosted_profile_image_url_large = cache_results['we_vote_hosted_profile_image_url_large']
    we_vote_hosted_profile_image_url_medium = cache_results['we_vote_hosted_profile_image_url_medium']
    we_vote_hosted_profile_image_url_tiny = cache_results['we_vote_hosted_profile_image_url_tiny']

    # Retrieve twitter user details from twitter
    results = retrieve_twitter_user_info(twitter_id, twitter_auth_response.twitter_screen_name)
    if not results['success']:
        twitter_json = {
            'id': twitter_id,
            'name': twitter_auth_response.twitter_name,
            'screen_name': twitter_auth_response.twitter_screen_name,
            'profile_image_url_https': twitter_auth_response.twitter_profile_image_url_https,
        }
    else:
        twitter_json = results['twitter_json']

    twitter_user_results = twitter_user_manager.update_or_create_twitter_user(
        twitter_json, twitter_id,
        cached_twitter_profile_image_url_https=cached_twitter_profile_image_url_https,
        cached_twitter_profile_banner_url_https=cached_twitter_profile_banner_url_https,
        we_vote_hosted_profile_image_url_large=we_vote_hosted_profile_image_url_large,
        we_vote_hosted_profile_image_url_medium=we_vote_hosted_profile_image_url_medium,
        we_vote_hosted_profile_image_url_tiny=we_vote_hosted_profile_image_url_tiny)

    status += twitter_user_results['status']
    if positive_value_exists(cached_twitter_profile_image_url_https):
        twitter_profile_image_url_https = cached_twitter_profile_image_url_https
    else:
        twitter_profile_image_url_https = twitter_auth_response.twitter_profile_image_url_https

    if success:
        twitter_profile_banner_url_https = ""
        try:
            twitter_profile_banner_url_https = twitter_user_results['twitter_user'].twitter_profile_banner_url_https
        except Exception:
            pass

        try:
            OrganizationManager.update_organization_single_voter_data(twitter_id,
                                                                      we_vote_hosted_profile_image_url_large,
                                                                      we_vote_hosted_profile_image_url_medium,
                                                                      we_vote_hosted_profile_image_url_tiny,
                                                                      twitter_profile_banner_url_https)
        except Exception as e:
            logger.error('twitter_sign_in_retrieve_for_api caught exception calling '
                         'update_organization_single_voter_data: '
                         '{error} [type: {error_type}]'.format(error=e, error_type=type(e)))

    json_data = {
        'success':                                  success,
        'status':                                   status,
        'voter_device_id':                          voter_device_id,
        'voter_we_vote_id':                         voter_we_vote_id,
        'voter_has_data_to_preserve':               voter_has_data_to_preserve,
        'existing_twitter_account_found':           existing_twitter_account_found,
        'voter_we_vote_id_attached_to_twitter':     voter_we_vote_id_attached_to_twitter,
        'twitter_sign_in_found':                    auth_response_results['twitter_auth_response_found'],
        'twitter_sign_in_verified':                 twitter_sign_in_verified,
        'twitter_sign_in_failed':                   twitter_sign_in_failed,
        'twitter_secret_key':                       twitter_secret_key,
        'twitter_access_secret':                    twitter_auth_response.twitter_access_secret,
        'twitter_access_token':                     twitter_auth_response.twitter_access_token,
        'twitter_id':                               twitter_id,
        'twitter_name':                             twitter_auth_response.twitter_name,
        'twitter_profile_image_url_https':          twitter_profile_image_url_https,
        'twitter_request_secret':                   twitter_auth_response.twitter_request_secret,
        'twitter_request_token':                    twitter_auth_response.twitter_request_token,
        'twitter_screen_name':                      twitter_auth_response.twitter_screen_name,
        'we_vote_hosted_profile_image_url_large':   we_vote_hosted_profile_image_url_large,
        'we_vote_hosted_profile_image_url_medium':  we_vote_hosted_profile_image_url_medium,
        'we_vote_hosted_profile_image_url_tiny':    we_vote_hosted_profile_image_url_tiny,
    }

    return json_data


def twitter_retrieve_ids_i_follow_for_api(voter_device_id):     # twitterRetrieveIdsIFollow
    """

    :param voter_device_id:
    :return:
    """
    success = False

    twitter_auth_manager = TwitterAuthManager()
    auth_response_results = twitter_auth_manager.retrieve_twitter_auth_response(voter_device_id)
    status = auth_response_results['status']
    if not auth_response_results['twitter_auth_response_found']:
        error_results = {
            'success':                  success,
            'status':                   status,
            'voter_device_id':          voter_device_id,
            'twitter_ids_i_follow':     [],
        }
        return error_results

    twitter_auth_response = auth_response_results['twitter_auth_response']

    if not twitter_auth_response.twitter_id:
        success = False
        error_results = {
            'success':                  success,
            'status':                   status,
            'voter_device_id':          voter_device_id,
            'twitter_ids_i_follow':     [],
        }
        return error_results

    twitter_user_manager = TwitterUserManager()

    # Now that voter is signed in, reach out to twitter to get up to 5000 ids of other twitter users
    twitter_ids_i_follow_results = twitter_user_manager.retrieve_twitter_ids_i_follow_from_twitter(
        twitter_auth_response.twitter_id, twitter_auth_response.twitter_access_token,
        twitter_auth_response.twitter_access_secret)
    status += ' ' + twitter_ids_i_follow_results['status']
    twitter_ids_i_follow = twitter_ids_i_follow_results['twitter_ids_i_follow']
    if twitter_ids_i_follow_results['success']:
        twitter_who_i_follow_results = twitter_user_manager.create_twitter_who_i_follow_entries(
            twitter_auth_response.twitter_id, twitter_ids_i_follow)
        status += ' ' + twitter_who_i_follow_results['status']
        success = twitter_who_i_follow_results['success']
    results = {
        'success':              success,
        'status':               status,
        'voter_device_id':      voter_device_id,
        'twitter_ids_i_follow': twitter_ids_i_follow
    }
    return results


def voter_twitter_save_to_current_account_for_api(voter_device_id):  # voterTwitterSaveToCurrentAccount
    """

    :param voter_device_id:
    :return:
    """
    status = ""
    success = False
    twitter_account_created = False
    twitter_link_to_organization_exists = False
    twitter_link_to_organization_twitter_id = 0

    # Get voter_id from the voter_device_id
    results = is_voter_device_id_valid(voter_device_id)
    if not results['success']:
        results = {
            'success':                  False,
            'status':                   "VALID_VOTER_DEVICE_ID_MISSING",
            'voter_device_id':          voter_device_id,
            'twitter_account_created':  twitter_account_created,
        }
        return results

    voter_manager = VoterManager()
    results = voter_manager.retrieve_voter_from_voter_device_id(voter_device_id)
    if not positive_value_exists(results['voter_found']):
        results = {
            'success':                  False,
            'status':                   "VALID_VOTER_MISSING",
            'voter_device_id':          voter_device_id,
            'twitter_account_created':  twitter_account_created,
        }
        return results

    voter = results['voter']

    twitter_user_manager = TwitterUserManager()
    twitter_results = twitter_user_manager.retrieve_twitter_link_to_voter(0, voter.we_vote_id)
    if twitter_results['twitter_link_to_voter_found']:
        # We are surprised to be here because we try to only call this routine from the WebApp if the Twitter Account
        #  isn't currently linked to any voter
        error_results = {
            'status':                   "TWITTER_OWNER_VOTER_FOUND_WHEN_NOT_EXPECTED",
            'success':                  False,
            'voter_device_id':          voter_device_id,
            'twitter_account_created':  twitter_account_created,
        }
        return error_results

    twitter_auth_manager = TwitterAuthManager()
    auth_response_results = twitter_auth_manager.retrieve_twitter_auth_response(voter_device_id)
    if not auth_response_results['twitter_auth_response_found']:
        error_results = {
            'status':                   "TWITTER_AUTH_RESPONSE_COULD_NOT_BE_FOUND",
            'success':                  False,
            'voter_device_id':          voter_device_id,
            'twitter_account_created':  twitter_account_created,
        }
        return error_results

    twitter_auth_response = auth_response_results['twitter_auth_response']

    # Make sure this Twitter id isn't linked to another voter
    twitter_collision_results = twitter_user_manager.retrieve_twitter_link_to_voter(twitter_auth_response.twitter_id)
    if twitter_collision_results['twitter_link_to_voter_found']:
        # If we are here, then there is in fact a twitter_link_to_voter tied to another voter account
        # We are surprised to be here because we try to only call this routine from the WebApp if the Twitter Account
        #  isn't currently linked to any voter
        error_results = {
            'status':                   "TWITTER_OWNER_VOTER_FOUND_FOR_ANOTHER_VOTER_WHEN_NOT_EXPECTED",
            'success':                  False,
            'voter_device_id':          voter_device_id,
            'twitter_account_created':  twitter_account_created,
        }
        return error_results

    link_results = twitter_user_manager.create_twitter_link_to_voter(twitter_auth_response.twitter_id,
                                                                     voter.we_vote_id)

    if not link_results['twitter_link_to_voter_saved']:
        error_results = {
            'status':                   link_results['status'],
            'success':                  False,
            'voter_device_id':          voter_device_id,
            'twitter_account_created':  twitter_account_created,
        }
        return error_results

    twitter_account_created = True
    twitter_link_to_voter = link_results['twitter_link_to_voter']

    # Update voter with cached Twitter info
    results = voter_manager.save_twitter_user_values(voter, twitter_auth_response)
    status += results['status'] + ", "
    success = results['success']
    voter = results['voter']

    # Now find out if there is an organization already linked to this Twitter account
    twitter_results = twitter_user_manager.retrieve_twitter_link_to_organization(voter.we_vote_id)
    if twitter_results['twitter_link_to_organization_found']:
        twitter_link_to_organization = twitter_results['twitter_link_to_organization']
        twitter_link_to_organization_exists = True
        twitter_link_to_organization_twitter_id = twitter_link_to_organization.twitter_id

        # If here, we know that this organization is not linked to another voter, so we can update the
        #  voter to connect to this organization
        # Is this voter already linked to another organization?
        if voter.linked_organization_we_vote_id:
            # We need to merge the twitter_link_to_organization.organization_we_vote_id with
            #  voter.linked_organization_we_vote_id
            if positive_value_exists(twitter_link_to_organization.organization_we_vote_id) and \
                    positive_value_exists(voter.linked_organization_we_vote_id) and \
                    twitter_link_to_organization.organization_we_vote_id != voter.linked_organization_we_vote_id:
                # We are here, so we know that we found a twitter_link_to_organization, but it doesn't match
                # the org linked to this voter. So we want to merge these two organizations.
                twitter_link_to_organization_organization_id = 0  # We calculate this in move_organization...
                voter_linked_to_organization_organization_id = 0  # We calculate this in move_organization...
                move_organization_to_another_complete_results = move_organization_to_another_complete(
                    twitter_link_to_organization_organization_id,
                    twitter_link_to_organization.organization_we_vote_id,
                    voter_linked_to_organization_organization_id,
                    voter.linked_organization_we_vote_id,
                    voter.id, voter.we_vote_id
                )
                status += " " + move_organization_to_another_complete_results['status']
                # We do not need to change voter.linked_organization_we_vote_id since we merged into that organization
        else:
            # Connect voter.linked_organization_we_vote_id with twitter_link_to_organization.organization_we_vote_id
            try:
                voter.linked_organization_we_vote_id = twitter_link_to_organization.organization_we_vote_id
                voter.save()
            except Exception as e:
                success = False
                status += "VOTER_LINKED_ORGANIZATION_WE_VOTE_ID_NOT_UPDATED "
    else:
        # If here, we know that a twitter_link_to_organization does not exist
        # 1) Try to find existing organization with twitter_user_id
        organization_manager = OrganizationManager()
        organization_from_twitter_id_old_results = organization_manager.retrieve_organization_from_twitter_user_id_old(
            twitter_auth_response.twitter_id
        )
        new_organization_ready = False
        if organization_from_twitter_id_old_results['organization_found']:
            new_organization = organization_from_twitter_id_old_results['organization']
            new_organization_ready = True
        else:
            # 2) Create organization with twitter_user_id
            organization_name = voter.get_full_name()
            organization_website = ""
            organization_twitter_handle = ""
            organization_email = ""
            organization_facebook = ""
            organization_image = voter.voter_photo_url()
            organization_type = INDIVIDUAL
            organization_manager = OrganizationManager()
            create_results = organization_manager.create_organization(
                organization_name, organization_website, organization_twitter_handle,
                organization_email, organization_facebook, organization_image, twitter_auth_response.twitter_id,
                organization_type)
            if create_results['organization_created']:
                # Add value to twitter_owner_voter.linked_organization_we_vote_id when done.
                new_organization = create_results['organization']
                new_organization_ready = True
            else:
                new_organization = Organization()
                status += "NEW_ORGANIZATION_COULD_NOT_BE_CREATED "

        if new_organization_ready:
            try:
                voter.linked_organization_we_vote_id = new_organization.organization_we_vote_id
                voter.save()
                # Create TwitterLinkToOrganization
                results = twitter_user_manager.create_twitter_link_to_organization(
                    twitter_auth_response.twitter_id, voter.linked_organization_we_vote_id)
                if results['twitter_link_to_organization_saved']:
                    status += "TwitterLinkToOrganization_CREATED_AFTER_ORGANIZATION_CREATE "
                    twitter_link_to_organization_exists = True
                    twitter_link_to_organization_twitter_id = twitter_auth_response.twitter_id
                else:
                    status += "TwitterLinkToOrganization_NOT_CREATED_AFTER_ORGANIZATION_CREATE "
            except Exception as e:
                status += "UNABLE_TO_UPDATE_VOTER_LINKED_ORGANIZATION_WE_VOTE_ID_OR_CREATE_TWITTER_LINK_TO_ORG "

    if twitter_link_to_organization_exists:
        organization_list_manager = OrganizationListManager()
        repair_results = organization_list_manager.repair_twitter_related_organization_caching(
            twitter_link_to_organization_twitter_id)
        status += repair_results['status']

    results = {
        'success':                  success,
        'status':                   status,
        'voter_device_id':          voter_device_id,
        'twitter_account_created':  twitter_account_created,
    }
    return results
