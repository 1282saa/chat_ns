# Copyright Amazon.com and its affiliates; all rights reserved.
# SPDX-License-Identifier: LicenseRef-.amazon.com.-AmznSL-1.0
# Licensed under the Amazon Software License  https://aws.amazon.com/asl/

import os
import json
from typing import Annotated
from aws_lambda_powertools.event_handler import BedrockAgentResolver
from aws_lambda_powertools.event_handler.openapi.params import Query, Body

app = BedrockAgentResolver()


@app.post("/escalate", description="used to escalate to live agent")
def escalate(email: Annotated[str, Query(description="Email address to look up")]
                        ) -> Annotated[bool, Body(description="Response only True/False")]:
    # Do the confirmation of Email to account on file
    # respond with status or prompt for call back number for agent assist
    if email == "test@thebigtest.com":
        response = True
    else:
        response = False
    return response

@app.post("/password_change", description="used for changing account password")
def password_change(email: Annotated[str, Query(description="Email address to look up")],
                 phone: Annotated[str, Query(description="Phone number to verifying account information")],
                        ) -> Annotated[str, Body(description="change the account password after getting all the required information from user")]:
    
    if email and phone:
        response = "Successfully change the account password."
    else:
        response = "Failed to change the password."
    return response


def lambda_handler(event, context):
    return app.resolve(event, context)


if __name__ == "__main__":
    openApiSchema = json.loads(app.get_openapi_json_schema(openapi_version="3.0.0"))

    # Get current path
    current_path = os.path.dirname(os.path.realpath(__file__))

  
    ## Because of following warning the openAPI schema version is not changing to 3.0.0. Following code is hack to change that version programmatically.
    ## UserWarning: You are using Pydantic v2, which is incompatible with OpenAPI schema 3.0. Forcing OpenAPI 3.1
    # if openApiSchema["openapi"] != "3.0.0":
    #     openApiSchema["openapi"] = "3.0.0"

    # Updated operationIds in OpenAPI spec, so that we don't get this exception:
    # HttpVerb__ActionName__OperationId should match tool name regex for Claude 3.5 : ^[a-zA-Z0-9_-]{1,64}$
    def fix_operation_ids(api_spec):
        # Iterate through all paths and methods
        for path in api_spec['paths']:
            for method in api_spec['paths'][path]:
                operation = api_spec['paths'][path][method]
                if 'operationId' in operation:
                    # Get current operationId
                    current_id = operation['operationId']
                    # Remove duplication by taking the first part before '_post'
                    if '_post' in current_id:
                        # Split by underscore and remove duplicates
                        parts = current_id.split('_')
                        # Keep only unique parts and add '_post' at the end
                        unique_parts = []
                        seen = set()
                        for part in parts[:-1]:  # Exclude the last 'post' part
                            if part not in seen:
                                unique_parts.append(part)
                                seen.add(part)
                        new_id = '_'.join(unique_parts + ['post'])
                        operation['operationId'] = new_id

        return api_spec
    

    openApiSchema = fix_operation_ids(openApiSchema)
    
    # Create new json file for the OpenAPI schema
    openapi_path = os.path.join(current_path, "openapi.json")
    with open(openapi_path, "w") as f:
        json.dump(openApiSchema, f, indent=4)