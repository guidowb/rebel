#!/usr/bin/env python

import aws
import cli
import sys
import json
import cloudformation
import config

""" OpsManager API """

def opsmgr_list_images(region = None):
	command = [
		'ec2',
		'describe-images',
		'--filters', 'Name=name,Values=pivotal-ops-manager-v*'
	]
	if region is not None:
		command.extend(['--region', region])
	images = json.loads(aws.aws_cli_verbose(command))["Images"]
	images = sorted(images, key=lambda image: image["CreationDate"])
	images.reverse()
	return images

def opsmgr_select_image(version):
	images = opsmgr_list_images()
	image = next((i for i in images if i["Name"].startswith("pivotal-ops-manager-v" + version)), None)
	return image

def opsmgr_launch_instance(stack, version=None, verbose=False):
	version = cloudformation.get_tag(stack, "pcf-version") if version is None else version
	image = opsmgr_select_image(version)
	if image is None:
		print "No ops-manager image found for version", version
		sys.exit(1)
	if verbose:
		print "Launching OpsMgr instance from", image["ImageId"] + ":", image["Description"]
	command = [
		'ec2',
		'run-instances',
		'--image-id', image["ImageId"],
		'--instance-type', 'm3.large',
		'--subnet-id', cloudformation.get_output(stack, "PcfPublicSubnetId"),
		'--associate-public-ip-address',
		'--block-device-mapping', 'DeviceName=/dev/sda1,Ebs={VolumeSize=100}',
		'--security-group-ids', cloudformation.get_output(stack, "PcfOpsManagerSecurityGroupId"),
		'--key-name', config.get('aws', 'nat-key-pair')
	]
	instance = json.loads(aws.aws_cli_verbose(command))["Instances"][0]
	command = [
		'ec2',
		'create-tags',
		'--resources', instance["InstanceId"],
		'--tags', 'Key=Name,Value=Ops Manager'
	]
	aws.aws_cli_verbose(command)
	return instance

""" OpsManager CLI exercising OpsManager API """

def list_images_cmd(argv):
	region = argv[1] if len(argv) > 1 else None
	images = opsmgr_list_images(region)
	print "\n".join([i["ImageId"] + " " + i["Name"] for i in images])

def deploy_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	stack = cloudformation.select_stack(stack_name)
	instance = opsmgr_launch_instance(stack, verbose=True)
	print "Launched instance", instance["InstanceId"]

commands = {
	"images": { "func": list_images_cmd, "usage": "images [<region>]" },
	"deploy": { "func": deploy_cmd,      "usage": "deploy <stack-name> <version>" },
}

if __name__ == '__main__':
	cli.cli(sys.argv, commands)