.PHONY: push push-cli push-booster push-all

# Push main platform (private)
push:
	git push origin main

# Push conduct-cli package to its public repo
push-cli:
	git subtree push --prefix=packages/conduct-cli conduct-cli main

# Push agent-booster package to its public repo
push-booster:
	git subtree push --prefix=tools/booster agent-booster main

# Push everything — platform + both public packages
push-all: push push-cli push-booster
