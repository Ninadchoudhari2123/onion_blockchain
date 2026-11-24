# Batch split/merge permission fix

## Root cause
The Batch Operations page selected the current holder as the actor, which was correct. However, the original role-permission configuration did not grant `BATCH_SPLIT` or `BATCH_MERGED` to the `FARMER` role. A farmer who had just created and still held a batch therefore saw `Permission denied`.

## Fix
- `FARMER` now has `BATCH_SPLIT` and `BATCH_MERGED` permissions.
- Split and merge still require the participant to be the current holder of every active batch involved.
- `COLLECTION_CENTER` and `WHOLESALER` retain their existing permissions.
- `TRANSPORTER` and `RETAILER` remain restricted from splitting and merging.
- The Batch Operations page now explains the role policy.

## Regression tests
Added tests proving that:
1. A farmer who currently holds a batch can split it and merge its child batches.
2. A transporter who currently holds a batch still cannot split it.
3. The existing collection-centre split/merge workflow still works.

Run tests with `pytest -q`.
