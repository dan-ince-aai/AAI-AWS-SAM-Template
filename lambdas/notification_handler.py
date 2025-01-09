import json
import boto3
import urllib3
import time

def send_response(event, context, response_status, reason=None, response_data=None, physical_resource_id=None):
    response_data = response_data or {}
    physical_resource_id = physical_resource_id or context.log_stream_name

    response_body = json.dumps({
        'Status': response_status,
        'Reason': reason or "See the details in CloudWatch Log Stream: {}".format(context.log_stream_name),
        'PhysicalResourceId': physical_resource_id,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'NoEcho': False,
        'Data': response_data
    })

    http = urllib3.PoolManager()
    try:
        response_url = event['ResponseURL']
        print(f"Sending response to {response_url}")
        response = http.request(
            'PUT',
            response_url,
            body=response_body,
            headers={'content-type': '', 'content-length': str(len(response_body))}
        )
        print(f"CloudFormation returned status code: {response.status}")
    except Exception as e:
        print("Failed to send the response to CloudFormation", e)

def lambda_handler(event, context):
    print(f"Received event: {json.dumps(event)}")
    
    try:
        if event['RequestType'] in ['Create', 'Update']:
            props = event['ResourceProperties']
            bucket_name = props['BucketName']
            notification_config = props['NotificationConfiguration']
            
            # Ensure notification config is properly formatted
            for config in notification_config.get('LambdaFunctionConfigurations', []):
                if not isinstance(config.get('Events', []), list):
                    config['Events'] = [config['Events']] if 'Events' in config else []
            
            print(f"Applying notification configuration: {json.dumps(notification_config)}")
            
            # Add a small delay to ensure Lambda permission is properly propagated
            time.sleep(5)
            
            s3 = boto3.client('s3')
            s3.put_bucket_notification_configuration(
                Bucket=bucket_name,
                NotificationConfiguration=notification_config
            )
            
            send_response(event, context, 'SUCCESS')
        elif event['RequestType'] == 'Delete':
            # On delete, remove the notification configuration
            props = event['ResourceProperties']
            bucket_name = props['BucketName']
            
            s3 = boto3.client('s3')
            s3.put_bucket_notification_configuration(
                Bucket=bucket_name,
                NotificationConfiguration={'LambdaFunctionConfigurations': []}
            )
            
            send_response(event, context, 'SUCCESS')
    except Exception as e:
        print(f"Error: {str(e)}")
        send_response(event, context, 'FAILED', reason=str(e))