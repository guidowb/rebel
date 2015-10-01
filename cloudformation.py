#!/usr/bin/env python

import sys
import pivnet
import config
import json
import aws
import cli

""" CloudFormation API """

def download_template(version):
	version = config.get('elastic-runtime', 'release') if version is None else version
	product = pivnet.pivnet_select_product('Elastic Runtime')
	release = pivnet.pivnet_select_release(product, version)
	files = pivnet.pivnet_files(product, release, 'cloudformation')
	if len(files) < 1:
		print "no cloudformation template found for release", version
		sys.exit(1)
	if len(files) > 1:
		print "multiple cloudformation templates found for release", version
		sys.exit(1)
	return json.load(pivnet.pivnet_open(files[0]))

def list_stacks(stack_pattern = ""):
	stacks = json.loads(aws.aws_cli_verbose(['cloudformation', 'describe-stacks']))["Stacks"]
	stacks = [s for s in stacks if is_ramble_stack(s)]
	stacks = [s for s in stacks if stack_pattern in s["StackName"]]
	return stacks

def select_stack(stack_pattern):
	stacks = list_stacks(stack_pattern)
	if len(stacks) < 1:
		print stack_pattern, "does not match any stacks. Available stacks are:"
		print "\n".join(["   " + s["StackName"] for s in list_stacks()])
		sys.exit(1)
	if len(stacks) > 1:
		print stack_pattern, "matches multiple stacks:"
		print "\n".join(["   " + s["StackName"] for s in stacks])
		print "Please be more specific"
		sys.exit(1)
	return stacks[0]

def create_stack(template, name):
	command = [
		'cloudformation',
		'create-stack',
		'--stack-name', name,
		'--template-body', json.dumps(template),
		'--on-failure', 'DO_NOTHING',
		'--parameters', json.dumps(get_parameters(template)),
		'--capabilities', 'CAPABILITY_IAM',
		'--tags', json.dumps(get_tags(template))
	]
	aws.aws_cli_verbose(command)

def delete_stack(stack):
	command = [
		'cloudformation',
		'delete-stack',
		'--stack-name', stack["StackName"]
	]
	aws.aws_cli_verbose(command)

def get_tags(template):
	""" CloudFormation limits us to 10 """
	tags = [
		{ "Key": "created-by", "Value": "ramble" },
	]
	return tags

def is_ramble_stack(stack):
	tags = stack.get("Tags", [])
	for tag in tags:
		key = tag.get("Key", None)
		value = tag.get("Value", None)
		if key == 'created-by' and value == 'ramble':
			return True
	return False

def get_parameters(template):
	parameters = []
	for key in template["Parameters"]:
		value = None
		if template["Parameters"][key].get("Default", None) is not None:
			value = config.get('aws', friendly_name(key), None)
		else:
			value = config.get('aws', friendly_name(key))
		if value is not None:
			parameters.append({
				"ParameterKey": key,
				"ParameterValue": config.get('aws', friendly_name(key)),
				"UsePreviousValue": False
				})
	return parameters

def friendly_name(oldname):
	""" Completely unnecessary but the template parameter names offend my sensibilities """
	newname = ""
	oldname = oldname.lstrip('0123456789') + "-"
	hasdash = True
	for i in range(len(oldname) - 1):
		c1 = oldname[i]
		c2 = oldname[i+1]
		if c1.isupper() and c2.islower() and not hasdash:
			newname += '-' + c1.lower()
		elif c1.islower() and c2.isupper():
			newname += c1 + '-'
			hasdash = True
		else:
			newname += c1.lower()
			hasdash = False
	return newname

""" CloudFormation CLI exercising CloudFormation API """

def list_stacks_cmd(argv):
	stack_pattern = argv[1] if len(argv) > 1 else ""
	stacks = list_stacks(stack_pattern)
	print "\n".join([s["StackName"] for s in stacks])

def create_stack_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	release = argv[2] if len(argv) > 2 else None
	template = download_template(release)
	create_stack(template, stack_name)

def delete_stack_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	stack_name = argv[1]
	stack = select_stack(stack_name)
	delete_stack(stack)

commands = {
	"stacks": { "func": list_stacks_cmd, "usage": "stacks [<stack-name>]" },
	"create-stack": { "func": create_stack_cmd, "usage": "create-stack <stack-name> [<release>]" },
	"delete-stack": { "func": delete_stack_cmd, "usage": "delete-stack <stack-name>" },
}

if __name__ == '__main__':
	cli.cli(sys.argv, commands)
