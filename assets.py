#!/usr/bin/env python

import cli
import sys
import aws
import json
import string

# hierarchy of resource types:
#
# instance < vpc
# instance < subnet
# instance < network-interface
# instance ~ security-groups
#
# network-interface < subnet
# network-interface ~ security-group
# netowrk-interface < attachment = instance

type_defs = {
	'vpc': {
		'id': 'VpcId',
		'list': [ 'ec2', 'describe-vpcs', 'Vpcs'],
		'delete': [ 'ec2', 'delete-vpc', '--vpc-id', '{}' ],
		'children': [
			{ 'type': 'network-interface', 'filter': [ '--filters', 'Name=vpc-id,Values={},Name=attachment.delete-on-termination,Values=false' ] },
			{ 'type': 'load-balancer',     'parent-ref': 'VPCId' },
			{ 'type': 'subnet',            'filter': [ '--filters', 'Name=vpc-id,Values={}' ]  },
			{ 'type': 'security-group',    'filter': [ '--filters', 'Name=vpc-id,Values={}' ]  },
		]
	},
	'network-interface': {
		'id': 'NetworkInterfaceId',
		'list': [ 'ec2', 'describe-network-interfaces', 'NetworkInterfaces' ],
		'delete': [ 'ec2', 'delete-network-interface', '--network-interface-id', '{}' ],
	},
	'load-balancer': {
		'id': 'LoadBalancerName',
		'list': [ 'elb', 'describe-load-balancers', 'LoadBalancerDescriptions' ],
		'delete': [ 'elb', 'delete-load-balancer', '--load-balancer-name', '{}' ],
	},
	'instance': {
		'id': 'InstanceId',
		'list': [ 'ec2', 'describe-instances', 'Reservations,Instances' ],
		'delete': [ 'ec2', 'terminate-instances', '--instance-ids', '{}' ],
		'children': [
			{ 'type': 'network-interface', 'filter': [ '--filters', 'Name=attachment.instance-id,Values={}' ]  },
		]
	},
	'subnet': {
		'id': 'SubnetId',
		'list': [ 'ec2', 'describe-subnets', 'Subnets' ],
		'delete': [ 'ec2', 'delete-subnet', '--subnet-id', '{}' ],
		'children': [
			{ 'type': 'instance', 'filter': [ '--filters', 'Name=subnet-id,Values={}' ]  },
		]
	},
	'security-group': {
		'id': 'GroupId',
		'list': [ 'ec2', 'describe-security-groups', 'SecurityGroups' ],
		'delete': [ 'ec2', 'delete-security-group', '--group-id', '{}' ],
	},
}

def get_array(type_name, type_def, parent, fields):
	items = parent.get(fields[0])
	items = items if items is not None else []
	if len(fields) == 1:
		return [
			{
				'type': type_name,
				'id': item.get(type_def["id"]),
				'item': item
			}
			for item in items
		]
	else:
		flattened = []
		for item in items:
			flattened += get_array(type_name, type_def, item, fields[1:])
		return flattened

def get_items(type_name, item_id=None, filter=[]):
	type_def = type_defs.get(type_name, None)
	if type_def is None:
		print "Unknown type", type_name
		sys.exit(1)
	container = json.loads(aws.aws_cli_verbose(type_def["list"][:-1] + filter))
	fields = string.split(type_def["list"][-1], ',')
	items = get_array(type_name, type_def, container, fields)
	if item_id is not None:
		items = [item for item in items if item["id"] == item_id]
	return items

def get_tree(type_name, item_id=None, filter=[]):
	items = get_items(type_name, item_id, filter)
	for item in items:
		type_def = type_defs.get(type_name)
		subtypes = type_def.get("children", [])
		for subtype in subtypes:
			subtype_name = subtype["type"]
			filter = subtype.get("filter", [])
			filter = [element.replace('{}', item["id"]) for element in filter]
			children = get_tree(subtype_name, filter=filter)
			parent_ref = subtype.get("parent-ref", None)
			if parent_ref is not None:
				children = [child for child in children if child["item"].get(parent_ref) == item["id"]]
			item["children"] = item.get("children", []) + children
	return items

def print_tree(tree, indent=0):
	for item in tree:
		print ' ' * indent + item["type"], item["id"]
		print_tree(item.get("children", []), indent + 3)

def list_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	type_name = argv[1]
	items = get_items(type_name)
	print '\n'.join([item["id"] for item in items])

def tree_cmd(argv):
	cli.exit_with_usage(argv) if len(argv) < 2 else None
	type_name = argv[1]
	item_id = argv[2] if len(argv) > 2 else None
	tree = get_tree(type_name, item_id)
	print_tree(tree)

commands = {
	"list":    { "func": list_cmd,    "usage": "list <type>" },
	"tree":    { "func": tree_cmd,    "usage": "tree <type> [<id>]" },
}

if __name__ == '__main__':
	cli.cli(sys.argv, commands)
