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

def opsmgr_select_image(version, verbose=False):
	images = opsmgr_list_images()
	image = next((i for i in images if i["Name"].startswith("pivotal-ops-manager-v" + version)), None)
	if verbose and image is None:
		print "No ops-manager image found for version", version
		if len(images) > 0:
			print "Available images are:"
			print "\n".join([i["ImageId"] + " " + i["Name"] for i in images])
		sys.exit(1)
	return image

def opsmgr_launch_instance(stack, version=None, verbose=False):
	version = cloudformation.get_tag(stack, "pcf-version") if version is None else version
	image = opsmgr_select_image(version, verbose)
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
	tags = [
		{ "Key": "Name", "Value": "Ops Manager" },
		{ "Key": "Stack", "Value": stack["StackName"] },
		{ "Key": "Image", "Value": image["Description"] }
	]
	command = [
		'ec2',
		'create-tags',
		'--resources', instance["InstanceId"],
		'--tags', json.dumps(tags)
	]
	aws.aws_cli_verbose(command)
	return instance

def opsmgr_find_instances(stack=None):
	filters = [
		{ "Name": "tag:Name", "Values": [ "Ops Manager" ] },
		{ "Name": "tag-key",  "Values": [ "Stack" ] },
		{ "Name": "instance-state-name", "Values": [ "pending", "running"] }
	]
	if stack is not None:
		filters.extend([ { "Name": "subnet-id", "Values": [ cloudformation.get_output(stack, "PcfPublicSubnetId") ] } ])
	command = [
		'ec2',
		'describe-instances',
		'--filters', json.dumps(filters)
	]
	reservations = json.loads(aws.aws_cli_verbose(command))["Reservations"]
	instances = []
	for r in reservations:
		instances += r["Instances"]
	return instances

def opsmgr_get_tag(instance, key):
	tags = instance["Tags"]
	tag = next((t for t in tags if t["Key"] == key), None)
	return tag["Value"] if tag is not None else None

""" OpsManager CLI exercising OpsManager API """

def list_images_cmd(argv):
	region = argv[1] if len(argv) > 1 else None
	images = opsmgr_list_images(region)
	print "\n".join([i["ImageId"] + " " + i["Name"] for i in images])

def launch_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	version = argv[2] if len(argv) > 2 else ""
	stack = cloudformation.select_stack(stack_name)
	instance = opsmgr_launch_instance(stack, version, verbose=True)
	print "Launched instance", instance["InstanceId"]

def list_instances_cmd(argv):
	instances = opsmgr_find_instances()
	for i in instances:
		print opsmgr_get_tag(i, "Stack") + "(" + i["InstanceId"] + ")", opsmgr_get_tag(i, "Image")

commands = {
	"images":    { "func": list_images_cmd,    "usage": "images [<region>]" },
	"launch":    { "func": launch_cmd,         "usage": "launch <stack-name> <version>" },
	"instances": { "func": list_instances_cmd, "usage": "instances" },
}

if __name__ == '__main__':
	cli.cli(sys.argv, commands)