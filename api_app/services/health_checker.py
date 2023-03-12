import logging
from typing import Tuple
from azure.core import exceptions
from azure.cosmos.aio import CosmosClient
from azure.servicebus.aio import ServiceBusClient
from azure.mgmt.compute.aio import ComputeManagementClient
from azure.cosmos.exceptions import CosmosHttpResponseError
from azure.servicebus.exceptions import ServiceBusConnectionError, ServiceBusAuthenticationError
from api.dependencies.database import get_store_key

from core import config, cloud
from models.schemas.status import StatusEnum
from resources import strings


async def create_state_store_status(credential) -> Tuple[StatusEnum, str]:
    status = StatusEnum.ok
    message = ""
    debug = True if config.DEBUG == "true" else False
    try:
        primary_master_key = await get_store_key(credential)
        cosmos_client = CosmosClient(config.STATE_STORE_ENDPOINT, primary_master_key, connection_verify=debug)
        async with cosmos_client:
            list_databases_response = cosmos_client.list_databases()
            [database async for database in list_databases_response]
    except exceptions.ServiceRequestError:
        status = StatusEnum.not_ok
        message = strings.STATE_STORE_ENDPOINT_NOT_RESPONDING
    except CosmosHttpResponseError:
        status = StatusEnum.not_ok
        message = strings.STATE_STORE_ENDPOINT_NOT_ACCESSIBLE
    except Exception:
        logging.exception("Failed to query cosmos db status")
        status = StatusEnum.not_ok
        message = strings.UNSPECIFIED_ERROR
    return status, message


async def create_service_bus_status(credential) -> Tuple[StatusEnum, str]:
    status = StatusEnum.ok
    message = ""
    try:
        service_bus_client = ServiceBusClient(config.SERVICE_BUS_FULLY_QUALIFIED_NAMESPACE, credential, retry_total=0)
        async with service_bus_client:
            receiver = service_bus_client.get_queue_receiver(queue_name=config.SERVICE_BUS_STEP_RESULT_QUEUE)
            async with receiver:
                pass
    except ServiceBusConnectionError:
        status = StatusEnum.not_ok
        message = strings.SERVICE_BUS_NOT_RESPONDING
    except ServiceBusAuthenticationError:
        status = StatusEnum.not_ok
        message = strings.SERVICE_BUS_AUTHENTICATION_ERROR
    except Exception:
        logging.exception("Failed to query service bus status")
        status = StatusEnum.not_ok
        message = strings.UNSPECIFIED_ERROR
    return status, message


async def create_resource_processor_status(credential) -> Tuple[StatusEnum, str]:
    status = StatusEnum.ok
    message = ""
    try:
        vmss_name = f"vmss-rp-porter-{config.TRE_ID}"
        compute_client = ComputeManagementClient(credential=credential,
                                                 subscription_id=config.SUBSCRIPTION_ID,
                                                 base_url=cloud.get_resource_manager_endpoint(),
                                                 credential_scopes=cloud.get_resource_manager_credential_scopes())
        async with compute_client:
            vmss_list = compute_client.virtual_machine_scale_set_vms.list(config.RESOURCE_GROUP_NAME, vmss_name)
            async for vm in vmss_list:
                instance_view = await compute_client.virtual_machine_scale_set_vms.get_instance_view(config.RESOURCE_GROUP_NAME, vmss_name, vm.instance_id)
                health_status = instance_view.vm_health.status.code
                if health_status != strings.RESOURCE_PROCESSOR_HEALTHY_MESSAGE:
                    status = StatusEnum.not_ok
                    message = strings.RESOURCE_PROCESSOR_GENERAL_ERROR_MESSAGE
    except Exception:
        logging.exception("Failed to query resource processor status")
        status = StatusEnum.not_ok
        message = strings.UNSPECIFIED_ERROR
    return status, message
