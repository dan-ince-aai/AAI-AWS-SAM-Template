import json
import os
import boto3
import http.client
import time
from urllib.parse import unquote_plus

# Initialize AWS services
s3_client = boto3.client('s3')

def get_presigned_url(bucket, key, expiration=3600):
    """Generate a presigned URL for the S3 object"""
    return s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket, 'Key': key},
        ExpiresIn=expiration
    )

def transcribe_audio(audio_url, api_key):
    """Transcribe audio using AssemblyAI API with http.client"""
    headers = {
        "authorization": api_key,
        "content-type": "application/json"
    }
    
    conn = http.client.HTTPSConnection("api.assemblyai.com")
    
    # Submit the audio file for transcription
    json_data = json.dumps({"audio_url": audio_url})
    conn.request("POST", "/v2/transcript", json_data, headers)
    response = conn.getresponse()
    
    if response.status != 200:
        raise Exception(f"Failed to submit audio for transcription: {response.read().decode()}")
    
    response_data = json.loads(response.read().decode())
    transcript_id = response_data['id']
    
    # Poll for transcription completion
    while True:
        conn = http.client.HTTPSConnection("api.assemblyai.com")
        conn.request("GET", f"/v2/transcript/{transcript_id}", headers=headers)
        polling_response = conn.getresponse()
        polling_data = json.loads(polling_response.read().decode())

        if polling_data['status'] == 'completed':
            conn.close()
            return polling_data['text']
        elif polling_data['status'] == 'error':
            conn.close()
            raise Exception(f"Transcription failed: {polling_data['error']}")
        
        conn.close()
        time.sleep(3)

def lambda_handler(event, context):
    """Lambda function to handle S3 events and process audio files"""
    try:
        # Get the AssemblyAI API key from environment variables
        api_key = os.environ.get('ASSEMBLYAI_API_KEY')
        if not api_key:
            raise ValueError("ASSEMBLYAI_API_KEY environment variable is not set")

        # Get the transcript bucket name from environment variables
        transcript_bucket = os.environ.get('TRANSCRIPT_BUCKET')
        if not transcript_bucket:
            raise ValueError("TRANSCRIPT_BUCKET environment variable is not set")

        # Process each record in the S3 event
        for record in event.get('Records', []):
            # Get the S3 bucket and key
            bucket = record['s3']['bucket']['name']
            key = unquote_plus(record['s3']['object']['key'])
            
            # Generate a presigned URL for the audio file
            audio_url = get_presigned_url(bucket, key)
            
            # Get the transcription from AssemblyAI
            transcript_text = transcribe_audio(audio_url, api_key)
            
            # Prepare the transcript filename
            transcript_key = f"{os.path.splitext(key)[0]}.txt"
            
            # Upload the transcript to S3
            s3_client.put_object(
                Bucket=transcript_bucket,
                Key=transcript_key,
                Body=transcript_text,
                ContentType='text/plain'
            )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Audio file(s) processed successfully",
                "detail": "Transcripts have been stored in the transcript bucket"
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Error processing audio file(s)",
                "error": str(e)
            })
        } 