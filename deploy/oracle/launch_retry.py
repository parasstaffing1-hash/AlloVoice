"""Land an Always Free ARM box via retry loop (capacity is scarce).

Prereqs: pip install oci ; configured ~/.oci/config (API key added in console:
Identity > Users > your user > API Keys). Then fill the OCIDs below and run:
  python3 launch_retry.py   (leave running; it tries every ~10 min)

Shape strategy: request 1 OCPU/6GB first (fits capacity gaps), resize to
2 OCPU/12GB in the console once it lands.
"""
import time

import oci

# ---- FILL THESE (console: copy OCIDs) ----
COMPARTMENT_ID = "ocid1.compartment.oc1..REPLACE"
SUBNET_ID = "ocid1.subnet.oc1.uk-london-1.REPLACE"   # VCN subnet with internet route
IMAGE_ID = "ocid1.image.oc1.uk-london-1.REPLACE"     # Ubuntu 24.04 ARM (Canonical)
AVAILABILITY_DOMAIN = "REPLACE"                      # e.g. hTfA:UK-LONDON-1-AD-1
SSH_PUBLIC_KEY = open("id_allovoice.pub").read().strip()

SHAPES = [
    {"ocpus": 1, "memory_gbs": 6},
    {"ocpus": 2, "memory_gbs": 12},
]

config = oci.config.from_file()
compute = oci.core.ComputeClient(config)

for shape in SHAPES:
    while True:
        try:
            resp = compute.launch_instance(
                oci.core.models.LaunchInstanceDetails(
                    compartment_id=COMPARTMENT_ID,
                    availability_domain=AVAILABILITY_DOMAIN,
                    shape="VM.Standard.A1.Flex",
                    shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
                        ocpus=shape["ocpus"], memory_in_gbs=shape["memory_gbs"]),
                    display_name="allovoice",
                    source_details=oci.core.models.InstanceSourceViaImageDetails(
                        source_type="image", image_id=IMAGE_ID),
                    create_vnic_details=oci.core.models.CreateVnicDetails(
                        subnet_id=SUBNET_ID, assign_public_ip=True),
                    metadata={"ssh_authorized_keys": SSH_PUBLIC_KEY},
                )
            )
            print("LANDED:", resp.data.id, shape)
            raise SystemExit(0)
        except oci.exceptions.ServiceError as e:
            # Out of capacity / throttled — expected, keep polling politely.
            print(f"shape {shape}: {e.status} {e.code} — retrying in 10 min")
            time.sleep(600)
