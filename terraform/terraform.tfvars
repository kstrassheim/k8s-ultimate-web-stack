app_name = "k8s-ultimate-web-stack"

# env is deliberately NOT set here.
#
# backend.key is "app-reg-${var.env}.tfstate", resolved at `tofu init`. A value
# in terraform.tfvars outranks TF_VAR_env, so pinning env here would make every
# environment init against app-reg-dev.tfstate -- test and prod would plan and
# apply over dev's state. The pipelines pass the environment via TF_VAR_env;
# locally the variable's own default ("dev") applies.
