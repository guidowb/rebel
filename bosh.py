#!/usr/bin/env python

import cli
import aws
import sys
import json
import opsmgr
import config
import cloudformation
import uuid

""" BOSH Configuration """

def output(stack, key):
	return cloudformation.get_output(stack, key)

def bosh_config(stack):
	settings = json.load(opsmgr.opsmgr_get(stack, "/api/installation_settings"))

	infrastructure = settings["infrastructure"]

	iaas_configuration = infrastructure["iaas_configuration"]
	iaas_configuration["access_key_id"]     = output(stack, "PcfIamUserAccessKey")
	iaas_configuration["secret_access_key"] = output(stack, "PcfIamUserSecretAccessKey")
	iaas_configuration["vpc_id"]            = output(stack, "PcfVpc")
	iaas_configuration["security_group"]    = get_security_group_name(output(stack, "PcfVmsSecurityGroupId"))
	iaas_configuration["key_pair_name"]     = output(stack, "PcfKeyPairName")
	iaas_configuration["ssh_private_key"]   = get_private_key()
	iaas_configuration["region"]            = output(stack, "PcfPublicSubnetAvailabilityZone")[:-1]
	iaas_configuration["encrypted"]         = False

	director_configuration = infrastructure["director_configuration"]
	director_configuration["ntp_servers"]  = [
		"0.amazon.pool.ntp.org",
		"1.amazon.pool.ntp.org",
		"2.amazon.pool.ntp.org",
		"3.amazon.pool.ntp.org",
	]
	director_configuration["resurrector_enabled"] = True
	director_configuration["blobstore_type"] = "s3"
	director_configuration["s3_blobstore_options"] = {
		"endpoint":    aws.get_s3_endpoint(iaas_configuration["region"]),
		"bucket_name": output(stack, "PcfOpsManagerS3Bucket"),
		"access_key":  output(stack, "PcfIamUserAccessKey"),
		"secret_key":  output(stack, "PcfIamUserSecretAccessKey"),
	}
	director_configuration["database_type"] = "external"
	director_configuration["external_database_options"] = {
		"host":     output(stack, "PcfRdsAddress"),
		"port":     output(stack, "PcfRdsPort"),
		"user":     output(stack, "PcfRdsUsername"),
		"password": output(stack, "PcfRdsPassword"),
		"database": output(stack, "PcfRdsDBName"),
	}

	infrastructure["availability_zones"] = [
		{
			"guid": get_guid(),
			"iaas_identifier": output(stack, "PcfPublicSubnetAvailabilityZone"),
		}
	]

	infrastructure["networks"] = [
		{
			"guid": get_guid(),
			"name": "PCFNetwork",
			"iaas_network_identifier": output(stack, "PcfPrivateSubnetId"),
			"subnet": "10.0.16.0/20",
			"reserved_ip_ranges": "10.0.16.1-10.0.16.9",
			"dns": "10.0.0.2",
			"gateway": "10.0.16.1",
		}
	]

	for p in settings.get("products", []):
		p["singleton_availability_zone_reference"] = infrastructure["availability_zones"][0]["guid"]
		p["deployment_network_reference"] = infrastructure["networks"][0]["guid"]
		p["infrastructure_network_reference"] = infrastructure["networks"][0]["guid"]

	opsmgr.opsmgr_post_yaml(stack, "/api/installation_settings", "installation[file]", settings)

	return settings

def get_security_group_name(group_id):
	command = [
		'ec2',
		'describe-security-groups',
		'--group-ids', group_id
	]
	group = json.loads(aws.aws_cli_verbose(command))["SecurityGroups"][0]
	return group["GroupName"]

def get_private_key():
	with open(config.get("aws", "ssh-private-key"), 'rb') as keyfile:
		return keyfile.read()

def get_guid():
	return uuid.uuid4().hex[:20]

""" BOSH Configuration CLI """

def config_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	stack = cloudformation.select_stack(stack_name)
	settings = bosh_config(stack)
	print json.dumps(settings, indent=4)

commands = {
	"config": { "func": config_cmd, "usage": "config <stack-name>" },
}

def settings_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	stack = cloudformation.select_stack(stack_name)
	if stack is None:
		print "Stack", stack_name, "not found"
		sys.exit(1)
	bosh_config(stack)

if __name__ == '__main__':
	cli.cli(sys.argv, commands)
