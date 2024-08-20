#!/bin/bash

BUCKET_NAME="bedrockappstack-testing-cloudfrontlogbucket095a165-dm8f6tuwnsto"
LOG_PATH=""

while true; do
    # Get the latest log file
    # Get the header
    latest_log=$(aws s3 ls s3://$BUCKET_NAME/$LOG_PATH --recursive | sort | tail -n 1 | awk '{print $4}')
    aws s3 cp s3://$BUCKET_NAME/$latest_log - | gunzip -c |  grep '#Fields'

    for log in $(aws s3 ls s3://$BUCKET_NAME/$LOG_PATH --recursive | sort | tail -n 10 | awk '{print $4}'); do
        echo $log
        aws s3 cp s3://$BUCKET_NAME/$log - | gunzip -c
    done
    latest_log=$(aws s3 ls s3://$BUCKET_NAME/$LOG_PATH --recursive | sort | tail -n 1 | awk '{print $4}')
    
    sleep 10
    clear
done
