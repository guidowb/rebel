#!/usr/bin/env python

import sys
import os
import stat
import errno
import urllib
import zipfile
import subprocess

def main(argv):
	try:
		output = aws_cli(argv[1:])
		print output
	except subprocess.CalledProcessError as error:
		print error.output
		sys.exit(error.returncode)

HOME_DIR = os.path.expanduser("~")
AWS_CLI_DIR = HOME_DIR + "/.aws-cli"
AWS_CLI_BIN = AWS_CLI_DIR + "/bin/aws"
AWS_CLI_ZIP = AWS_CLI_DIR + "/aws.zip"
AWS_CLI_URL = "https://s3.amazonaws.com/aws-cli/awscli-bundle.zip"
AWS_CLI_INSTALL = AWS_CLI_DIR + "/awscli-bundle/install"

def aws_cli(argv):
	install_aws_cli_if_required()
	return subprocess.check_output([AWS_CLI_BIN] + argv, stderr=subprocess.STDOUT)

def install_aws_cli_if_required():
	if os.path.isfile(AWS_CLI_BIN) and os.access(AWS_CLI_BIN, os.X_OK):
		return
	print "Installing AWS CLI"
	mkdir_p(AWS_CLI_DIR)
	print "   Downloading latest"
	urllib.urlretrieve(AWS_CLI_URL, AWS_CLI_ZIP)
	print "   Extracting"
	zipfile.ZipFile(AWS_CLI_ZIP, 'r').extractall(AWS_CLI_DIR)
	print "   Installing"
	os.chmod(AWS_CLI_INSTALL, stat.S_IXUSR | stat.S_IRUSR)
	subprocess.check_output([AWS_CLI_INSTALL, "-i", AWS_CLI_DIR])
	version = subprocess.check_output([AWS_CLI_BIN, "--version"], stderr=subprocess.STDOUT).rstrip()
	print "   Version:", version
	print "   Done"

def mkdir_p(dir):
	try:
		os.makedirs(AWS_CLI_DIR)
	except os.error, e:
		if e.errno != errno.EEXIST:
			raise

if __name__ == '__main__':
	main(sys.argv)