"""NDK shared bridges, plus optional USB Moto dynamic source/saved execution."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/scratch/android-shared"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ndk", type=Path, default=Path.home() / "Android/Sdk/ndk/28.2.13676358")
    parser.add_argument("--serial", choices=["ZE2223BQZT"])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for name in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS", "SESSION_MANAGER"):
        env.pop(name, None)
    env.update(HARMONY_DESKTOP_RECOVERY="0", YUE_DESKTOP_RECOVERY="0")
    toolchain = Path(env.get("ZIRAN_ROOT", ROOT / "../../ziran")).resolve()
    ziran = Path(env.get("ZIRAN_BIN", toolchain / "build/bin/ziran"))
    tools = args.ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin"
    assert (args.ndk / "build/cmake/android.toolchain.cmake").is_file(), "Android NDK required"

    def run(command, name, *, capture=False):
        print(name, flush=True)
        log = OUT / (name + ".log")
        with log.open("w") as stream:
            result = subprocess.run(list(map(str, command)), cwd=ROOT, env=env,
                                    stdout=stream, stderr=subprocess.STDOUT, timeout=1800)
        if result.returncode:
            with log.open("rb") as stream:
                stream.seek(max(0, log.stat().st_size - 5000))
                print(stream.read(5000).decode(errors="replace"), flush=True)
            raise SystemExit(f"{name}: exit {result.returncode}; {log}")
        if capture:
            assert log.stat().st_size < 65536, log
            return log.read_text().strip()

    packages = {name: run([ziran, "pkg", "path", name, "--offline"], "path-" + name, capture=True)
                for name in ("libavif", "libaom", "dav1d", "image_codec")}
    project = OUT / "consumer"
    project.mkdir(exist_ok=True)
    (project / "CMakeLists.txt").write_text('''cmake_minimum_required(VERSION 3.22)
project(AndroidSharedAVIF C CXX ASM)
include("${AVIF_PACKAGE}/native/ZiranAvif.cmake")
ziran_avif_add_native(AVIF_SOURCE "${AVIF_SOURCE}" AOM_SOURCE "${AOM_SOURCE}"
    DAV1D_SOURCE "${DAV1D_SOURCE}" BUILD_SHARED_BRIDGE)
''')
    remote = "/data/local/tmp/ziran-avif-shared-test"
    abis = []
    if args.serial:
        abis = run(["adb", "-s", args.serial, "shell", "getprop", "ro.product.cpu.abilist"],
                   "phone-abis", capture=True).split(",")
    for abi, prefix, define, machine in (("armeabi-v7a", "armv7a-linux-androideabi", "__arm__", "ARM"),
                                         ("arm64-v8a", "aarch64-linux-android", "__aarch64__", "AArch64")):
        build = OUT / abi
        run(["cmake", "-S", project, "-B", build,
             f"-DCMAKE_TOOLCHAIN_FILE={args.ndk}/build/cmake/android.toolchain.cmake",
             f"-DANDROID_ABI={abi}", "-DANDROID_PLATFORM=android-21", "-DCMAKE_BUILD_TYPE=Release",
             f"-DAVIF_PACKAGE={ROOT}", f"-DAVIF_SOURCE={packages['libavif']}",
             f"-DAOM_SOURCE={packages['libaom']}", f"-DDAV1D_SOURCE={packages['dav1d']}",
             "-DZIRAN_AVIF_DAV1D_JOBS=1"], abi + "-configure")
        run(["cmake", "--build", build, "--target", "avif_bridge", "--parallel", "2"], abi + "-bridge")
        library = build / "libavif_bridge.so"
        header = run([tools / "llvm-readelf", "-h", library], abi + "-elf", capture=True)
        assert machine in header, header
        segments = run([tools / "llvm-readelf", "-lW", library], abi + "-segments", capture=True)
        loads = [line for line in segments.splitlines() if line.strip().startswith("LOAD ")]
        assert loads and all(int(line.split()[-1], 16) >= 16384 for line in loads), segments
        module_args = ["--module-path", f"avif={ROOT}/src", "--module-path", str(ROOT / "src"),
                       "--module-path", f"image_codec={packages['image_codec']}/src",
                       "--module-path", f"std={toolchain}/std"]
        definitions = ["--target-os", "android", "--target-cpu",
                       "arm64" if abi == "arm64-v8a" else "none",
                       "--define", "ANDROID_BUILD", "--define", define]
        ir = build / "dynamic-ir"
        run([ziran, "ir", "--root", ROOT / "tests", *module_args, *definitions,
             "-o", ir, ROOT / "tests/dynamic.zi"], abi + "-ir")
        binaries = []
        for form in ("source", "saved"):
            source = ROOT / "tests/dynamic.zi" if form == "source" else ir / "dynamic.zir"
            generated = build / form
            imports = module_args if form == "source" else ["--module-path", str(ir)]
            run([ziran, "build", "--target=c", "--entry", "dynamic:main", "--prune-stale", "--root", source.parent, *imports, *definitions,
                 "-o", generated, source], abi + "-" + form + "-generate")
            sources = sorted(generated.rglob("*.c"))
            binary = generated / "dynamic"
            run([tools / (prefix + "21-clang"), "-std=c11", "-O1", "-fPIE", "-pie",
                 "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections", "-Wl,--no-undefined", "-I" + str(toolchain / "include"),
                 *["-iquote" + str(path) for path in sorted({p.parent for p in sources})],
                 *sources, "-ldl", "-lm", "-o", binary], abi + "-" + form + "-link")
            dependencies = run([tools / "llvm-readelf", "-d", binary], abi + "-" + form + "-dependencies", capture=True)
            assert "libavif" not in dependencies and "libaom" not in dependencies, dependencies
            binaries.append((form, binary))
        if abi in abis:
            adb = ["adb", "-s", args.serial]
            try:
                run([*adb, "shell", "mkdir", "-p", remote + "/fixtures"], "phone-directory")
                run([*adb, "push", library, remote + "/libavif_bridge.so"], abi + "-phone-library")
                names = ["rgba8", "rgba10", "rgba12", "gray8", "gray10", "gray12", "transform00",
                         "transform01", "transform10", "transform11", "transform20", "transform21",
                         "transform30", "transform31", "premultiplied", "opaque", "animated"]
                fixtures = [ROOT / "tests/fixtures" / (name + suffix) for name in names
                            for suffix in (".avif", ".strict.rgba")]
                run([*adb, "push", *fixtures, remote + "/fixtures/"], "phone-fixtures")
                for form, binary in binaries:
                    run([*adb, "push", binary, remote + "/dynamic"], abi + "-" + form + "-phone-binary")
                    run([*adb, "shell", "chmod", "700", remote + "/dynamic"], "phone-executable")
                    command = ["timeout", "60", remote + "/dynamic", remote + "/libavif_bridge.so", remote + "/fixtures"]
                    run([*adb, "shell", shlex.join(command)], abi + "-" + form + "-phone-test")
                    print(f"PASS {abi} {form}: Moto dlopen and 17 exact pixel/error/ABI cases", flush=True)
            finally:
                run([*adb, "shell", "rm", "-rf", remote], "phone-cleanup")
        print(f"PASS {abi}: NDK shared bridge, 16 KB alignment and source/saved dynamic consumers", flush=True)
    if args.serial:
        assert "armeabi-v7a" in abis or "arm64-v8a" in abis, "Moto has no supported ABI"
    print("Android shared bridge local tests passed" + (" with Moto execution" if args.serial else "; device execution not requested"))


if __name__ == "__main__":
    main()
