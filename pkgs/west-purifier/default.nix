{
  lib,
  stdenvNoCC,
  makeWrapper,
  runtimeShell,
  python3,
  nix-prefetch-git,
  nix,
  gh,
  git,
  cacert,
  original,
  tool,
  sdkVersion,
  nixpkgsSrc,
  purifierSrc,
}:
stdenvNoCC.mkDerivation {
  pname = "west-purifier";
  version = "0.1.0";
  src = ../..;
  nativeBuildInputs = [ makeWrapper ];
  dontBuild = true;
  installPhase = ''
    mkdir -p "$out/bin" "$out/lib/west-purifier"
    cp -r west_purifier nix lib-overlays pkgs native "$out/lib/west-purifier/"
    install -m755 bin/west-purifier "$out/bin/west-purifier"
    for file in realize release; do
      substituteInPlace "$out/lib/west-purifier/nix/$file.nix" --replace-fail '@nixpkgs@' '${nixpkgsSrc}' --replace-fail '@purifier@' '${purifierSrc}'
    done
    wrapProgram "$out/bin/west-purifier" \
      --prefix PATH : ${
        lib.makeBinPath [
          python3
          nix
          gh
          git
        ]
      } \
      --set-default SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --set-default WEST_PURIFIER_GH ${gh}/bin/gh \
      --set WEST_PURIFIER_PREFETCH_GIT ${nix-prefetch-git}/bin/nix-prefetch-git \
      --set WEST_PURIFIER_ORIGINAL ${original} \
      --set WEST_PURIFIER_SHELL ${runtimeShell} \
      --set WEST_PURIFIER_TOOL_SITE ${tool}/${python3.sitePackages} \
      --set WEST_PURIFIER_TOOL ${tool} \
      --set WEST_PURIFIER_PYTHON ${original}/bin/python \
      --set WEST_PURIFIER_SDK_VERSION ${sdkVersion} \
      --set WEST_PURIFIER_SDK "$out"
    for program in ${tool}/bin/west; do
      name=$(basename "$program")
      makeWrapper "$out/bin/west-purifier" "$out/bin/$name" --add-flags "--native=$name"
    done
  '';
  meta = {
    description = "Native West with locked Nix-resolved Git projects";
    homepage = "https://nix-purifiers.github.io/";
    license = lib.licenses.mit;
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
    ];
    mainProgram = "west-purifier";
  };
}
