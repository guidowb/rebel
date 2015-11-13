#!/usr/bin/env python

import os
import cli
import sys
import json
import aws
import config
import opsmgr
import cloudformation

from tempfile import SpooledTemporaryFile as tempfile

""" CF Elastic Runtime Configuration """

def output(stack, key):
	return cloudformation.get_output(stack, key)

def first_of(stack, keys):
	for key in keys:
		output = cloudformation.get_output(stack, key)
		if output is not None:
			return output
	return None

def find(properties, key):
	properties = [ p for p in properties if p["identifier"] == key ]
	if len(properties) < 1:
		return None
	return properties[0]

def set(properties, key, value):
	if properties is None:
		return
	prop = find(properties, key)
	if prop is None:
		return
	prop["value"] = value

def cf_config(stack, version=None):
	opsmgr.opsmgr_install_if_needed(stack, "cf", "Elastic Runtime", version)

	settings = json.load(opsmgr.opsmgr_get(stack, "/api/installation_settings"))

	aws_region = output(stack, "PcfPublicSubnetAvailabilityZone")[:-1]

	infrastructure = settings["infrastructure"]
	elastic_runtime = find(settings["products"], "cf")

	elastic_runtime["availability_zone_references"] = [ az["guid"] for az in infrastructure["availability_zones"]]
	elastic_runtime["singleton_availability_zone_reference"] = infrastructure["availability_zones"][0]["guid"]
	elastic_runtime["network_reference"] = infrastructure["networks"][0]["guid"]

	create_cf_databases(stack)

	database_configuration = find(elastic_runtime["properties"], "system_database")
	database_configuration["value"] = "external"
	database_options = find(database_configuration["options"], "external")["properties"]
	set(database_options, "host", output(stack, "PcfRdsAddress"))
	set(database_options, "port", output(stack, "PcfRdsPort"))
	set(database_options, "username", output(stack, "PcfRdsUsername"))
	set(database_options, "password", { "secret": output(stack, "PcfRdsPassword") })

	blobstore_configuration = find(elastic_runtime["properties"], "system_blobstore")
	blobstore_configuration["value"] = "external"
	blobstore_options = find(blobstore_configuration["options"], "external")["properties"]
	set(blobstore_options, "endpoint",          aws.get_s3_endpoint(aws_region))
	set(blobstore_options, "access_key",        output(stack, "PcfIamUserAccessKey"))
	set(blobstore_options, "secret_key",        { "secret": output(stack, "PcfIamUserSecretAccessKey") })
	# For PCF 1.5 and prior
	set(blobstore_options, "bucket", first_of(stack, ["PcfElasticRuntimeS3Bucket", "PcfElasticRuntimeS3ResourcesBucket"]))
	# For PCF 1.6 and beyond
	set(blobstore_options, "buildpacks_bucket", first_of(stack, ["PcfElasticRuntimeS3BuildpacksBucket", "PcfElasticRuntimeS3Bucket"]))
	set(blobstore_options, "droplets_bucket",   first_of(stack, ["PcfElasticRuntimeS3DropletsBucket",   "PcfElasticRuntimeS3Bucket"]))
	set(blobstore_options, "packages_bucket",   first_of(stack, ["PcfElasticRuntimeS3PackagesBucket",   "PcfElasticRuntimeS3Bucket"]))
	set(blobstore_options, "resources_bucket",  first_of(stack, ["PcfElasticRuntimeS3ResourcesBucket",  "PcfElasticRuntimeS3Bucket"]))

	set(elastic_runtime["properties"], "logger_endpoint_port", 4443)
	set(elastic_runtime["properties"], "allow_cross_container_traffic", True)

	router_configuration = find(elastic_runtime["jobs"], "router")
	router_configuration["elb_names"] = find_load_balancer(stack, output(stack, "PcfElbDnsName"))["LoadBalancerName"]
	router_settings = router_configuration["properties"]
	set(router_settings, "enable_ssl", True)

	controller_settings = find(elastic_runtime["jobs"], "cloud_controller")["properties"]
	set(controller_settings, "system_domain", config.get("cf", "system-domain", stack=stack["StackName"]))
	set(controller_settings, "apps_domain",   config.get("cf", "apps-domain", stack=stack["StackName"]))
	set(controller_settings, "allow_app_ssh_access", True)

	ssh_elb_name = output(stack, "PcfElbSshDnsName")
	if ssh_elb_name is not None:
		diego_brain_settings = find(elastic_runtime["jobs"], "diego_brain")
		if diego_brain_settings is not None:
			diego_brain_settings["elb_names"] = find_load_balancer(stack, ssh_elb_name)["LoadBalancerName"]

	haproxy_settings = find(elastic_runtime["jobs"], "ha_proxy")["properties"]
	set(haproxy_settings, "ssl_rsa_certificate", {
		"private_key_pem": get_private_key(stack),
		"cert_pem": get_server_certificate(stack)
		})
	set(haproxy_settings, "skip_cert_verify", True)

	set_instances(elastic_runtime, "nfs_server",  0)
	set_instances(elastic_runtime, "mysql_proxy", 0)
	set_instances(elastic_runtime, "mysql",       0)
	set_instances(elastic_runtime, "ccdb",        0)
	set_instances(elastic_runtime, "uaadb",       0)
	set_instances(elastic_runtime, "consoledb",   0)
	set_instances(elastic_runtime, "ha_proxy",    0)

	opsmgr.opsmgr_post_yaml(stack, "/api/installation_settings", "installation[file]", settings)

	return settings

def set_instances(settings, job_name, count):
	job = find(settings["jobs"], job_name)
	set(job["instances"], "instances", count)

def find_load_balancer(stack, dns_name):
	command = [
		'elb',
		'describe-load-balancers'
	]
	load_balancers = json.loads(aws.aws_cli_verbose(command))["LoadBalancerDescriptions"]
	load_balancers = [ lb for lb in load_balancers if lb["DNSName"] == dns_name]
	if len(load_balancers) != 1:
		print "Could not resolve load balancer for dns name", dns_name
		sys.exit(1)
	return load_balancers[0]

def get_server_certificate(stack):
	certificate_arn  = config.get("aws", "ssl-certificate-arn", stack=stack["StackName"])
	certificate_name = certificate_arn.split('/')[-1]
	command = [
		'iam',
		'get-server-certificate',
		'--server-certificate-name', certificate_name
	]
	certificate = json.loads(aws.aws_cli_verbose(command))["ServerCertificate"]
	certificate_body = certificate["CertificateBody"]
	return certificate_body

def get_private_key(stack):
	keyfilepath = config.get("cf", "ssl-certificate-private-key", stack=stack["StackName"])
	keyfilepath = os.path.expanduser(keyfilepath)
	with open(keyfilepath, 'rb') as keyfile:
		return keyfile.read()

def create_cf_databases(stack):
	databases = [
		'uaa',
		'ccdb',
		'console',
		'notifications',
		'autoscale',
		'app_usage_service'
	]
	try:
		sql = tempfile()
		for database in databases:
			sql.write('create database if not exists ' + database + ';\n')
		sql.seek(0)
		command = [
			'mysql',
			'--host=' + output(stack, "PcfRdsAddress"),
			'--user=' + output(stack, "PcfRdsUsername"),
			'--password=' + output(stack, "PcfRdsPassword")
		]
		opsmgr.opsmgr_exec(stack, command, stdin=sql)
	finally:
		sql.close()

""" CF Elastic Runtime Configuration CLI """

def config_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	version = argv[2] if len(argv) > 2 else ""
	stack = cloudformation.select_stack(stack_name)
	settings = cf_config(stack, version)
	print json.dumps(settings, indent=4)

commands = {
	"config": { "func": config_cmd, "usage": "config <stack-name> [<version>]" },
}

if __name__ == '__main__':
	cli.cli(sys.argv, commands)
