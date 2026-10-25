"""Create a convenience ZIP from the verified source distribution."""

import tarfile
import zipfile
from pathlib import Path

from check_dist import check


def main() -> None:
    dist = Path(__file__).resolve().parents[1] / "dist"
    sources = list(dist.glob("*.tar.gz"))
    if not sources:
        raise ValueError("Build the source distribution first")
    for source in sources:
        destination = source.with_name(source.name.removesuffix(".tar.gz") + ".zip")
        with tarfile.open(source) as archive:
            check(archive.getnames())
            with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as output:
                for member in archive.getmembers():
                    if member.isfile():
                        stream = archive.extractfile(member)
                        if stream is not None:
                            with stream:
                                output.writestr(member.name, stream.read())
        print(destination)


if __name__ == "__main__":
    main()
