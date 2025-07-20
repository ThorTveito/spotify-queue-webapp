#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { InfraStack } from '../lib/infra-stack';

const app = new cdk.App();
new InfraStack(app, 'spotify-queue-webapp-stack', {
  env: { region: 'eu-west-1' },
});
