# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Effectful interface to boto.
"""

import os
from characteristic import attributes, Attribute
from twisted.python.filepath import FilePath
from effect import Effect, sync_performer, TypeDispatcher
from effect.do import do

import boto


@attributes([
    "bucket",
    "prefix",
    "target_prefix",
])
class UpdateS3RoutingRule(object):
    """
    Update a routing rule for an S3 bucket website endpoint to point to a new
    path.

    If the path is changed, return the old path.

    :ivar bytes bucket: Name of bucket to change routing rule for.
    :ivar bytes prefix: Prefix to change routing rule for.
    :ivar bytes target_prefix: Target prefix to redirect to.
    """


@sync_performer
def perform_update_s3_routing_rule(dispatcher, intent):
    """
    See :class:`UpdateS3RoutingRule`.
    """
    s3 = boto.connect_s3()
    bucket = s3.get_bucket(intent.bucket)
    config = bucket.get_website_configuration_obj()
    rule = [rule for rule in config.routing_rules if
            rule.condition.key_prefix == intent.prefix][0]
    if rule.redirect.replace_key_prefix == intent.target_prefix:
        return None
    else:
        old_prefix = rule.redirect.replace_key_prefix
        rule.redirect.replace_key_prefix = intent.target_prefix
        bucket.set_website_configuration(config)
        return old_prefix


@attributes([
    "cname",
    "paths",
])
class CreateCloudFrontInvalidation(object):
    """
    Create a CloudFront invalidation request.

    :ivar bytes cname: A CNAME associated to the distribution to create an
        invalidation for.
    :ivar list paths: List of paths to invalidate.
    """


@sync_performer
def perform_create_cloudfront_invalidation(dispatcher, intent):
    """
    See :class:`CreateCloudFrontInvalidation`.
    """
    cf = boto.connect_cloudfront()
    distribution = [dist for dist in cf.get_all_distributions()
                    if intent.cname in dist.cnames][0]
    cf.create_invalidation_request(distribution.id, intent.paths)


@attributes([
    "bucket",
    Attribute("prefix", default_value=""),
    "keys",
])
class DeleteS3Keys(object):
    """
    Delete a list of keys from an S3 bucket.
    :ivar bytes bucket: Name of bucket to delete keys from.
    :ivar bytes prefix: Prefix to add to each key to delete.
    :ivar list keys: List of keys to be deleted.
    """


@sync_performer
def perform_delete_s3_keys(dispatcher, intent):
    """
    See :class:`DeleteS3Keys`.
    """
    s3 = boto.connect_s3()
    bucket = s3.get_bucket(intent.bucket)
    bucket.delete_keys(
        [intent.prefix + key
         for key in intent.keys])


@attributes([
    "source_bucket",
    Attribute("source_prefix", default_value=""),
    "destination_bucket",
    Attribute("destination_prefix", default_value=""),
    "keys",
])
class CopyS3Keys(object):
    """
    Copy a list of keys from one S3 bucket to another.

    :ivar bytes source_bucket: Name of bucket to copy keys from.
    :ivar bytes source_prefix: Prefix to add to each key to in
        ``source_bucket``.
    :ivar bytes destination_bucket: Name of bucket to copy keys to.
    :ivar bytes destination_prefix: Prefix to add to each key to in
        ``destination_bucket``.
    :ivar list keys: List of keys to be copied.
    """


@sync_performer
def perform_copy_s3_keys(dispatcher, intent):
    """
    See :class:`CopyS3Keys`.
    """
    s3 = boto.connect_s3()
    destination_bucket = s3.get_bucket(intent.destination_bucket)
    for key in intent.keys:
        destination_bucket.copy_key(
            new_key_name=intent.destination_prefix + key,
            src_bucket_name=intent.source_bucket,
            src_key_name=intent.source_prefix + key)


@attributes([
    "bucket",
    "prefix",
])
class ListS3Keys(object):
    """
    List the S3 keys in a bucket.

    Note that this returns a list with the prefixes stripped.

    :ivar bytes bucket: Name of bucket to list keys from.
    :ivar bytes prefix: Prefix of keys to be listed.
    """


@sync_performer
def perform_list_s3_keys(dispatcher, intent):
    """
    See :class:`ListS3Keys`.
    """
    s3 = boto.connect_s3()
    bucket = s3.get_bucket(intent.bucket)
    return {key.name[len(intent.prefix):]
            for key in bucket.list(intent.prefix)}


@attributes([
    "source_bucket",
    "source_prefix",
    "target_path",
    "filter_extensions",
])
class DownloadS3KeyRecursively(object):
    """
    Download the S3 files from a key in a bucket to a given directory.

    :ivar bytes source_bucket: Name of bucket to download keys from.
    :ivar bytes source_prefix: Download only files with this prefix.
    :ivar FilePath target_path: Directory to download files to.
    :ivar tuple filter_extensions: Download only files with extensions in this
        tuple.
    """


@sync_performer
@do
def perform_download_s3_key_recursively(dispatcher, intent):
    """
    See :class:`DownloadS3KeyRecursively`.
    """
    keys = yield Effect(
        ListS3Keys(prefix=intent.source_prefix + '/',
                   bucket=intent.source_bucket))
    for key in keys:
        if not key.endswith(intent.filter_extensions):
            continue
        path = intent.target_path.preauthChild(key)

        if not path.parent().exists():
            path.parent().makedirs()
        source_key = os.path.join(intent.source_prefix, key)
        yield Effect(
            DownloadS3Key(source_bucket=intent.source_bucket,
                          source_key=source_key,
                          target_path=path))


@attributes([
    "source_bucket",
    "source_key",
    "target_path",
])
class DownloadS3Key(object):
    """
    Download a file from S3.

    :ivar bytes source_bucket: Name of bucket to download key from.
    :ivar bytes source_key: Name of key to download.
    :ivar FilePath target_path: Path to download file to.
    """


@sync_performer
def perform_download_s3_key(dispatcher, intent):
    """
    See :class:`DownloadS3Key`.
    """
    s3 = boto.connect_s3()

    bucket = s3.get_bucket(intent.source_bucket)
    key = bucket.get_key(intent.source_key)
    with intent.target_path.open('w') as target_file:
        key.get_contents_to_file(target_file)


@attributes([
    "source_path",
    "target_bucket",
    "target_key",
    "files",
])
class UploadToS3Recursively(object):
    """
    Upload contents of a directory to S3, for given files.

    Note that this returns a list with the prefixes stripped.

    :ivar FilePath source_path: Prefix of files to be uploaded.
    :ivar bytes target_bucket: Name of bucket to upload file to.
    :ivar bytes target_key: Name S3 key to upload file to.
    :ivar list files: List of bytes, filenames to upload.
    """


@sync_performer
@do
def perform_upload_s3_key_recursively(dispatcher, intent):
    """
    See :class:`UploadToS3Recursively`.
    """
    for path in intent.source_path.walk():
        if path.basename() in intent.files:
            if path.isfile():
                yield Effect(
                    UploadToS3(
                        source_path=intent.source_path,
                        target_bucket=intent.target_bucket,
                        target_key=intent.target_key,
                        file=path,
                        ))


@attributes([
    "source_path",
    "target_bucket",
    "target_key",
    "file",
])
class UploadToS3(object):
    """
    Upload a file to S3.

    :ivar FilePath source_path: See :class:`UploadToS3Recursively`.
    :ivar bytes target_bucket: See :class:`UploadToS3 Recursively`.
    :ivar bytes target_key: See :class:`UploadToS3Recursively`.
    :ivar FilePath file: Path to file to upload.
    """


@sync_performer
def perform_upload_s3_key(dispatcher, intent):
    """
    See :class:`UploadToS3`.
    """
    s3 = boto.connect_s3()
    bucket = s3.get_bucket(intent.target_bucket)
    with intent.file.open() as source_file:
        key = bucket.new_key(intent.target_key +
                             intent.file.path[len(intent.source_path.path):])
        key.set_contents_from_file(source_file)
        key.make_public()

boto_dispatcher = TypeDispatcher({
    UpdateS3RoutingRule: perform_update_s3_routing_rule,
    ListS3Keys: perform_list_s3_keys,
    DeleteS3Keys: perform_delete_s3_keys,
    CopyS3Keys: perform_copy_s3_keys,
    DownloadS3KeyRecursively: perform_download_s3_key_recursively,
    DownloadS3Key: perform_download_s3_key,
    UploadToS3Recursively: perform_upload_s3_key_recursively,
    UploadToS3: perform_upload_s3_key,
    CreateCloudFrontInvalidation: perform_create_cloudfront_invalidation,
})


@attributes([
    Attribute('routing_rules'),
    Attribute('s3_buckets'),
])
class FakeAWS(object):
    """
    Enough of a fake implementation of AWS to test
    :func:`admin.release.publish_docs`.

    :ivar routing_rules: Dictionary of routing rules for S3 buckets. They are
        represented as dictonaries mapping key prefixes to replacements. Other
        types of rules and attributes are supported or represented.
    :ivar s3_buckets: Dictionary of fake S3 buckets. Each bucket is represented
        as a dictonary mapping keys to contents. Other attributes are ignored.
    :ivar cloudfront_invalidations: List of
        :class:`CreateCloudFrontInvalidation` that have been requested.
    """
    def __init__(self):
        self.cloudfront_invalidations = []

    @sync_performer
    def _perform_update_s3_routing_rule(self, dispatcher, intent):
        """
        See :class:`UpdateS3RoutingRule`.
        """
        old_target = self.routing_rules[intent.bucket][intent.prefix]
        self.routing_rules[intent.bucket][intent.prefix] = intent.target_prefix
        return old_target

    @sync_performer
    def _perform_create_cloudfront_invalidation(self, dispatcher, intent):
        """
        See :class:`CreateCloudFrontInvalidation`.
        """
        self.cloudfront_invalidations.append(intent)

    @sync_performer
    def _perform_delete_s3_keys(self, dispatcher, intent):
        """
        See :class:`DeleteS3Keys`.
        """
        bucket = self.s3_buckets[intent.bucket]
        for key in intent.keys:
            del bucket[intent.prefix + key]

    @sync_performer
    def _perform_copy_s3_keys(self, dispatcher, intent):
        """
        See :class:`CopyS3Keys`.
        """
        source_bucket = self.s3_buckets[intent.source_bucket]
        destination_bucket = self.s3_buckets[intent.destination_bucket]
        for key in intent.keys:
            destination_bucket[intent.destination_prefix + key] = (
                source_bucket[intent.source_prefix + key])

    @sync_performer
    def _perform_list_s3_keys(self, dispatcher, intent):
        """
        See :class:`ListS3Keys`.
        """
        bucket = self.s3_buckets[intent.bucket]
        return {key[len(intent.prefix):]
                for key in bucket
                if key.startswith(intent.prefix)}

    @sync_performer
    def _perform_download_s3_key(self, dispatcher, intent):
        """
        See :class:`DownloadS3Key`.
        """
        bucket = self.s3_buckets[intent.source_bucket]
        intent.target_path.setContent(bucket[intent.source_key])

    @sync_performer
    def _perform_upload_s3_key(self, dispatcher, intent):
        """
        See :class:`UploadToS3`.
        """
        bucket = self.s3_buckets[intent.target_bucket]
        with intent.file.open() as source_file:
            bucket[intent.target_key + intent.file.path[
                   len(intent.source_path.path):]] = source_file.read()

    def get_dispatcher(self):
        """
        Get an :module:`effect` dispatcher for interacting with this
        :class:`FakeAWS`.
        """
        # TODO make it more explicit what is real and what is fake
        return TypeDispatcher({
            # Share implementation with real implementation
            DownloadS3KeyRecursively: perform_download_s3_key_recursively,
            UploadToS3Recursively: perform_upload_s3_key_recursively,

            # Fake implementation
            UpdateS3RoutingRule: self._perform_update_s3_routing_rule,
            ListS3Keys: self._perform_list_s3_keys,
            DeleteS3Keys: self._perform_delete_s3_keys,
            CopyS3Keys: self._perform_copy_s3_keys,
            DownloadS3Key: self._perform_download_s3_key,
            UploadToS3: self._perform_upload_s3_key,
            CreateCloudFrontInvalidation:
                self._perform_create_cloudfront_invalidation,
        })
