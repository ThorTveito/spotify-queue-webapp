import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2'
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as sm from 'aws-cdk-lib/aws-secretsmanager'
import * as acm from 'aws-cdk-lib/aws-certificatemanager'
import { Construct } from 'constructs';
import { RetentionDays } from 'aws-cdk-lib/aws-logs';

export class InfraStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const repo = new ecr.Repository(this, 'DockerRepo', { repositoryName: 'spotify-queue-webapp' });

    // Create a cluster
    const vpc = new ec2.Vpc(this, 'Vpc', { maxAzs: 2 });

    const cluster = new ecs.Cluster(this, 'EcsCluster', { vpc });
    cluster.addCapacity('DefaultAutoScalingGroup', {
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3A, ec2.InstanceSize.MICRO),
      desiredCapacity: 1
    });

    const secret = sm.Secret.fromSecretNameV2(this, 'MySecret', 'spotify-queue-webapp-secrets');
    const secretNames = [
      "SPOTIFY_ACCESS_TOKEN",
      "SPOTIFY_REFRESH_TOKEN",
      "SPOTIFY_CLIENT_ID",
      "SPOTIFY_CLIENT_SECRET",
      "SPOTIFY_REDIRECT_URI",
    ]

    // Create Task Definition
    const taskDefinition = new ecs.Ec2TaskDefinition(this, 'TaskDef');
    secret.grantRead(taskDefinition.taskRole)

    const secrets: { [name: string]: ecs.Secret } = {}
    for (const name of secretNames) {
      secrets[name] = ecs.Secret.fromSecretsManager(secret, name)
    }

    const container = taskDefinition.addContainer('web', {
      image: ecs.ContainerImage.fromEcrRepository(repo, 'latest'),
      memoryLimitMiB: 256,
      logging: ecs.LogDriver.awsLogs({
        streamPrefix: 'spotify-queue-webapp', // Required: prefix for log stream name
        logRetention: RetentionDays.ONE_DAY, // Optional: retain logs for 1 week
      }),
      secrets: secrets
    });

    container.addPortMappings({
      containerPort: 8080,
      hostPort: 0,
      protocol: ecs.Protocol.TCP
    });

    // Create Service
    const service = new ecs.Ec2Service(this, "Service", {
      cluster,
      taskDefinition,
    });

    const targetGroup = new elbv2.ApplicationTargetGroup(this, 'ECS', {
      vpc,
      targets: [service.loadBalancerTarget({
        containerName: container.containerName,
        containerPort: 8080
      })],
      protocol: elbv2.ApplicationProtocol.HTTP,
    });
    // Create ALB
    const lb = new elbv2.ApplicationLoadBalancer(this, 'LB', {
      vpc,
      internetFacing: true,

    });
    const listener = lb.addListener('PublicListener', { port: 80, open: true, protocol: elbv2.ApplicationProtocol.HTTP, defaultTargetGroups: [targetGroup] });
    const secureListener = lb.addListener('SecureListener', {
      port: 443, certificates: [
        acm.Certificate.fromCertificateArn(this, '*.tvei.to-cert', 'arn:aws:acm:eu-west-1:968382676337:certificate/c04c3c8a-1342-4013-bebf-a00ed558e4ee')
      ],
      protocol: elbv2.ApplicationProtocol.HTTPS,
      defaultTargetGroups: [targetGroup]
    })

    // Attach ALB to ECS Service

    new cdk.CfnOutput(this, 'LoadBalancerDNS', { value: lb.loadBalancerDnsName, });
  }
}
