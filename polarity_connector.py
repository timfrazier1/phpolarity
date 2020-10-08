#!/usr/bin/python
# -*- coding: utf-8 -*-
# -----------------------------------------
# Phantom sample App Connector python file
# -----------------------------------------

# Python 3 Compatibility imports
from __future__ import print_function, unicode_literals

# Phantom App imports
import phantom.app as phantom
from phantom.base_connector import BaseConnector
from phantom.action_result import ActionResult

# Usage of the consts file is recommended
# from polarity_consts import *
import requests
import json
from bs4 import BeautifulSoup


class RetVal(tuple):

    def __new__(cls, val1, val2=None):
        return tuple.__new__(RetVal, (val1, val2))


class PolarityConnector(BaseConnector):

    def __init__(self):

        # Call the BaseConnectors init first
        super(PolarityConnector, self).__init__()

        self._state = None

        # Variable to hold a base_url in case the app makes REST calls
        # Do note that the app json defines the asset config, so please
        # modify this as you deem fit.
        self._base_url = None

    def initialize(self):
        # Load the state in initialize, use it to store data
        # that needs to be accessed across actions
        # self._state = self.load_state()

        # get the asset config
        config = self.get_config()
        self._verify = config["verify_server_cert"]
        self._base_url = "https://" + config.get('polarity_server')

        self._session = requests.Session()
        auth_data = {"identification": config["username"], "password": config["password"]}

        self.save_progress("Getting token for session...")
        try:
            auth_resp = self._session.post(self._base_url + "/v1/authenticate", json=auth_data, verify=self._verify)
            # auth_resp_json = auth_resp.json()
            self.debug_print(auth_resp)
        except Exception as e:
            return self.set_status(phantom.APP_ERROR, "Failed to get session cookie: ", e)

        self.debug_print(self._session.headers)
        return phantom.APP_SUCCESS

    def finalize(self):
        # Save the state, this data is saved across actions and app upgrades
        # self.save_state(self._state)
        ret_val, resp = self._make_rest_call('/v1/authenticate', self, method='delete')
        return phantom.APP_SUCCESS

    def _process_empty_response(self, response, action_result):
        if response.status_code == 200:
            return RetVal(phantom.APP_SUCCESS, {})

        return RetVal(
            action_result.set_status(
                phantom.APP_ERROR, "Empty response and no information in the header"
            ), None
        )

    def _process_html_response(self, response, action_result):
        # An html response, treat it like an error
        status_code = response.status_code

        try:
            soup = BeautifulSoup(response.text, "html.parser")
            error_text = soup.text
            split_lines = error_text.split('\n')
            split_lines = [x.strip() for x in split_lines if x.strip()]
            error_text = '\n'.join(split_lines)
        except:
            error_text = "Cannot parse error details"

        message = "Status Code: {0}. Data from server:\n{1}\n".format(status_code, error_text)

        message = message.replace(u'{', '{{').replace(u'}', '}}')
        return RetVal(action_result.set_status(phantom.APP_ERROR, message), None)

    def _process_json_response(self, r, action_result):
        # Try a json parse
        try:
            resp_json = r.json()
        except Exception as e:
            return RetVal(
                action_result.set_status(
                    phantom.APP_ERROR, "Unable to parse JSON response. Error: {0}".format(str(e))
                ), None
            )

        # Please specify the status codes here
        if 200 <= r.status_code < 399:
            return RetVal(phantom.APP_SUCCESS, resp_json)

        # You should process the error returned in the json
        message = "Error from server. Status Code: {0} Data from server: {1}".format(
            r.status_code,
            r.text.replace(u'{', '{{').replace(u'}', '}}')
        )

        return RetVal(action_result.set_status(phantom.APP_ERROR, message), None)

    def _process_response(self, r, action_result):
        # store the r_text in debug data, it will get dumped in the logs if the action fails
        if hasattr(action_result, 'add_debug_data'):
            action_result.add_debug_data({'r_status_code': r.status_code})
            action_result.add_debug_data({'r_text': r.text})
            action_result.add_debug_data({'r_headers': r.headers})

        # Process each 'Content-Type' of response separately

        # Process a json response
        if 'json' in r.headers.get('Content-Type', ''):
            return self._process_json_response(r, action_result)

        # Process an HTML response, Do this no matter what the api talks.
        # There is a high chance of a PROXY in between phantom and the rest of
        # world, in case of errors, PROXY's return HTML, this function parses
        # the error and adds it to the action_result.
        if 'html' in r.headers.get('Content-Type', ''):
            return self._process_html_response(r, action_result)

        # it's not content-type that is to be parsed, handle an empty response
        if not r.text:
            return self._process_empty_response(r, action_result)

        # everything else is actually an error at this point
        message = "Can't process response from server. Status Code: {0} Data from server: {1}".format(
            r.status_code,
            r.text.replace('{', '{{').replace('}', '}}')
        )

        return RetVal(action_result.set_status(phantom.APP_ERROR, message), None)

    def _make_rest_call(self, endpoint, action_result, method="get", **kwargs):
        # **kwargs can be any additional parameters that requests.request accepts

        config = self.get_config()

        resp_json = None

        try:
            request_func = getattr(self._session, method)
        except AttributeError:
            return RetVal(
                action_result.set_status(phantom.APP_ERROR, "Invalid method: {0}".format(method)),
                resp_json
            )

        # Create a URL to connect to
        url = self._base_url + endpoint

        try:
            r = request_func(
                url,
                # auth=(username, password),  # basic authentication
                verify=config.get('verify_server_cert', False),
                **kwargs
            )
        except Exception as e:
            return RetVal(
                action_result.set_status(
                    phantom.APP_ERROR, "Error Connecting to server. Details: {0}".format(str(e))
                ), resp_json
            )

        return self._process_response(r, action_result)

    def _handle_test_connectivity(self, param):
        # Add an action result object to self (BaseConnector) to represent the action for this param
        action_result = self.add_action_result(ActionResult(dict(param)))

        # NOTE: test connectivity does _NOT_ take any parameters
        # i.e. the param dictionary passed to this handler will be empty.
        # Also typically it does not add any data into an action_result either.
        # The status and progress messages are more important.

        self.save_progress("Connecting to list channels endpoint")

        # config = self.get_config()
        # make rest call
        ret_val, response = self._make_rest_call('/v2/channels', action_result, params=None, headers=None)

        if phantom.is_fail(ret_val):
            # the call to the 3rd party device or service failed, action result should contain all the error details
            # for now the return is commented out, but after implementation, return from here
            self.save_progress("Test Connectivity Failed.")
            return action_result.get_status()
        elif response.get("meta", False):
            # Return success
            self.save_progress("Number of channels: " + str(response["meta"]["page"]["number"]))
            self.save_progress("Test Connectivity Passed")
            return action_result.set_status(phantom.APP_SUCCESS)
        else:
            self.save_progress("Test Connectivity Failed.")
            action_result.set_status(
                    phantom.APP_ERROR, "Error Connecting to server. Details: {0}".format(str(response))
                )

    def _handle_search_items(self, param):
        # Implement the handler here
        # use self.save_progress(...) to send progress messages back to the platform
        self.save_progress("In action handler for: {0}".format(self.get_action_identifier()))

        # Add an action result object to self (BaseConnector) to represent the action for this param
        action_result = self.add_action_result(ActionResult(dict(param)))

        # Access action parameters passed in the 'param' dictionary

        # Required values can be accessed directly
        search_string = param['search_string'].lower()
        channel_id = param.get('channel_id', None)
        if channel_id:
            filter_string = search_string + '&filter[tag-entity-pair.channel-id]=' + channel_id
        else:
            filter_string = search_string

        # Optional values should use the .get() function
        # optional_parameter = param.get('optional_parameter', 'default_value')

        # make rest call
        ret_val, response = self._make_rest_call(
            '/v2/searchable-items?filter[entity.entity-name-lower]=' + filter_string, action_result, params=None, headers=None
        )

        if phantom.is_fail(ret_val):
            return action_result.get_status()

        try:
            for each_item in response['data']:
                action_result.add_data(each_item)
        except:
            action_result.add_data(response)
            return action_result.set_status(phantom.APP_ERROR, "Unable to parse data correctly.")

        # Add a dictionary that is made up of the most important values from data into the summary
        summary = action_result.update_summary({})
        summary['items_found'] = len(response['data'])

        # Return success, no need to set the message, only the status
        # BaseConnector will create a textual message based off of the summary dictionary
        return action_result.set_status(phantom.APP_SUCCESS)

    def _handle_get_annotations(self, param):
        # Implement the handler here
        # use self.save_progress(...) to send progress messages back to the platform
        self.save_progress("In action handler for: {0}".format(self.get_action_identifier()))

        action_result = self.add_action_result(ActionResult(dict(param)))

        # Access action parameters passed in the 'param' dictionary

        # Required values can be accessed directly
        entity_name = param['entity_name'].lower()

        ret_val, response = self._make_rest_call(
            '/v2/entities?filter[entity.entity-name-lower]=' + entity_name, action_result, params=None, headers=None
        )

        if phantom.is_fail(ret_val):
            return action_result.get_status()

        if len(response['data']) > 0:
            for item in response['data']:
                entity_id = item['id']
                ret_val, item_response = self._make_rest_call(
                        '/v2/entities/' + entity_id, action_result, params=None, headers=None)

                if phantom.is_fail(ret_val):
                    return action_result.get_status()

                """ Generate full results:
                item_result = {"tags": [], "channels": [], "tag-entity-pairs": []}
                for item in item_response["included"]:
                    if item["type"] == "tags":
                        item_result["tags"].append(item)
                    elif item["type"] == "channels":
                        item_result["channels"].append(item)
                    elif item["type"] == "tag-entity-pairs":
                        item_result["tag-entity-pairs"].append(item)

                action_result.add_data(item_result)

                summary = action_result.update_summary({})
                summary['num_tags'] = 0
                summary['num_tags'] += len(item_result['tags'])
                """
                # Return Tag names only:
                summary = action_result.update_summary({})
                summary['num_annotations'] = 0
                for item in item_response["included"]:
                    if item["type"] == "tags":
                        action_result.add_data({"annotation_name": item["attributes"]["tag-name"]})
                        summary['num_annotations'] += 1

            return action_result.set_status(phantom.APP_SUCCESS)

        else:
            action_result.add_data(response)
            return action_result.set_status(phantom.APP_SUCCESS, "Entity not found")

    def _handle_create_channel(self, param):
        # use self.save_progress(...) to send progress messages back to the platform
        self.save_progress("In action handler for: {0}".format(self.get_action_identifier()))

        # Add an action result object to self (BaseConnector) to represent the action for this param
        action_result = self.add_action_result(ActionResult(dict(param)))

        # Required values can be accessed directly
        channel_name = param['channel_name']
        channel_description = param.get('description', 'No description provided.')

        data = {
                "data": {
                    "type": "channels",
                    "attributes": {
                        "channel-name": channel_name,
                        "description": channel_description
                    }
                }
        }

        # make rest call
        ret_val, response = self._make_rest_call(
            '/v2/channels', action_result, method="post", json=data, params=None, headers=None
        )

        if phantom.is_fail(ret_val):
            # the call to the 3rd party device or service failed, action result should contain all the error details
            # for now the return is commented out, but after implementation, return from here
            return action_result.get_status()

        action_result.add_data(response['data'])

        # Add a dictionary that is made up of the most important values from data into the summary
        summary = action_result.update_summary({})
        summary['channel_id'] = response['data']['id']
        summary['channel_name'] = response['data']['attributes']['channel-name']

        return action_result.set_status(phantom.APP_SUCCESS)

    def _handle_list_channels(self, param):
        # Implement the handler here
        # use self.save_progress(...) to send progress messages back to the platform
        self.save_progress("In action handler for: {0}".format(self.get_action_identifier()))

        # Add an action result object to self (BaseConnector) to represent the action for this param
        action_result = self.add_action_result(ActionResult(dict(param)))

        # Optional values should use the .get() function
        channel_name = param.get('channel_name', '')

        if channel_name:
            endpoint = '/v2/channels?filter[channel.channel-name]=' + channel_name
        else:
            endpoint = '/v2/channels'

        # make rest call
        ret_val, response = self._make_rest_call(endpoint, action_result, params=None, headers=None)

        if phantom.is_fail(ret_val):
            return action_result.get_status()

        try:
            for item in response['data']:
                action_result.add_data(item)
        except:
            action_result.add_data(response)
            return action_result.set_status(phantom.APP_ERROR, "Unable to process response data.  Check inputs")

        # Add a dictionary that is made up of the most important values from data into the summary
        summary = action_result.update_summary({})
        summary['num_channels'] = len(response['data'])

        # Return success, no need to set the message, only the status
        # BaseConnector will create a textual message based off of the summary dictionary
        return action_result.set_status(phantom.APP_SUCCESS)

    def _handle_update_annotation(self, param):
        # Implement the handler here
        # use self.save_progress(...) to send progress messages back to the platform
        self.save_progress("In action handler for: {0}".format(self.get_action_identifier()))

        # Add an action result object to self (BaseConnector) to represent the action for this param
        action_result = self.add_action_result(ActionResult(dict(param)))

        # Access action parameters passed in the 'param' dictionary

        # Required values can be accessed directly
        entity = param['entity']
        annotation = param['annotation']
        channel_id = param['channel_id']
        data_type = param['type']
        if data_type != "ip" and data_type != "string":
            return action_result.set_status(phantom.APP_ERROR, "Type parameter must be either 'ip' or 'string'")

        data = {
                "data": [
                    {
                        "type": "tag-entity-pairs",
                        "attributes": {
                            "entity": entity,
                            "tag": annotation,
                            "channel-id": [channel_id],
                            "type": data_type,
                            # "confidence": 0,
                            # "doi-start": "2018-02-01",
                            # "doi-end": "2018-03-04"
                        }
                    }
                ]
        }

        # make rest call
        ret_val, response = self._make_rest_call(
            '/v2/tag-entity-pairs', action_result, method="post", json=data, params=None, headers=None
        )

        if phantom.is_fail(ret_val):
            return action_result.get_status()

        action_result.add_data(response)

        # Add a dictionary that is made up of the most important values from data into the summary
        summary = action_result.update_summary({})
        summary['status'] = "Created"

        return action_result.set_status(phantom.APP_SUCCESS)

    def handle_action(self, param):
        ret_val = phantom.APP_SUCCESS

        # Get the action that we are supposed to execute for this App Run
        action_id = self.get_action_identifier()

        self.debug_print("action_id", self.get_action_identifier())

        if action_id == 'test_connectivity':
            ret_val = self._handle_test_connectivity(param)

        elif action_id == 'search_items':
            ret_val = self._handle_search_items(param)

        elif action_id == 'get_annotations':
            ret_val = self._handle_get_annotations(param)

        elif action_id == 'create_channel':
            ret_val = self._handle_create_channel(param)

        elif action_id == 'list_channels':
            ret_val = self._handle_list_channels(param)

        elif action_id == 'update_annotation':
            ret_val = self._handle_update_annotation(param)

        return ret_val


def main():
    import pudb
    import argparse

    pudb.set_trace()

    argparser = argparse.ArgumentParser()

    argparser.add_argument('input_test_json', help='Input Test JSON file')
    argparser.add_argument('-u', '--username', help='username', required=False)
    argparser.add_argument('-p', '--password', help='password', required=False)

    args = argparser.parse_args()
    session_id = None

    username = args.username
    password = args.password

    if username is not None and password is None:

        # User specified a username but not a password, so ask
        import getpass
        password = getpass.getpass("Password: ")

    if username and password:
        try:
            login_url = PolarityConnector._get_phantom_base_url() + '/login'

            print("Accessing the Login page")
            r = requests.get(login_url, verify=False)
            csrftoken = r.cookies['csrftoken']

            data = dict()
            data['username'] = username
            data['password'] = password
            data['csrfmiddlewaretoken'] = csrftoken

            headers = dict()
            headers['Cookie'] = 'csrftoken=' + csrftoken
            headers['Referer'] = login_url

            print("Logging into Platform to get the session id")
            r2 = requests.post(login_url, verify=False, data=data, headers=headers)
            session_id = r2.cookies['sessionid']
        except Exception as e:
            print("Unable to get session id from the platform. Error: " + str(e))
            exit(1)

    with open(args.input_test_json) as f:
        in_json = f.read()
        in_json = json.loads(in_json)
        print(json.dumps(in_json, indent=4))

        connector = PolarityConnector()
        connector.print_progress_message = True

        if session_id is not None:
            in_json['user_session_token'] = session_id
            connector._set_csrf_info(csrftoken, headers['Referer'])

        ret_val = connector._handle_action(json.dumps(in_json), None)
        print(json.dumps(json.loads(ret_val), indent=4))

    exit(0)


if __name__ == '__main__':
    main()
