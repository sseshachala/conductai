.PHONY: push push-cli push-booster push-all

# Push main platform (private)
push:
	git push origin main

# Push conduct-cli package to its public repo
push-cli:
	git subtree split --prefix=packages/conduct-cli --rejoin -b _subtree/conduct-cli
	git push conduct-cli _subtree/conduct-cli:main

# Push agent-booster package to its public repo
push-booster:
	git subtree split --prefix=tools/booster --rejoin -b _subtree/agent-booster
	git push agent-booster _subtree/agent-booster:main

# Push everything — platform + both public packages
push-all: push push-cli push-booster
