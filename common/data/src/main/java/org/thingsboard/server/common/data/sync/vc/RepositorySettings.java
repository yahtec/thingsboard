// SPDX-FileCopyrightText: Copyright The Thingsboard Authors
// SPDX-License-Identifier: Apache-2.0
package org.thingsboard.server.common.data.sync.vc;

import lombok.Data;
import lombok.ToString;

import java.io.Serializable;

@Data
public class RepositorySettings implements Serializable {
    private static final long serialVersionUID = -3211552851889198721L;

    private String repositoryUri;
    private RepositoryAuthMethod authMethod;
    private String username;
    // Secrets excluded from toString — DefaultGitSyncService and others log
    // the full settings object on init failure at ERROR level, which would
    // ship the SSH private key and passwords to centralized log storage.
    @ToString.Exclude
    private String password;
    private String privateKeyFileName;
    @ToString.Exclude
    private String privateKey;
    @ToString.Exclude
    private String privateKeyPassword;
    private String defaultBranch;
    private boolean readOnly;
    private boolean showMergeCommits;
    private boolean localOnly;

    public RepositorySettings() {
    }

    public RepositorySettings(RepositorySettings settings) {
        this.repositoryUri = settings.getRepositoryUri();
        this.authMethod = settings.getAuthMethod();
        this.username = settings.getUsername();
        this.password = settings.getPassword();
        this.privateKeyFileName = settings.getPrivateKeyFileName();
        this.privateKey = settings.getPrivateKey();
        this.privateKeyPassword = settings.getPrivateKeyPassword();
        this.defaultBranch = settings.getDefaultBranch();
        this.readOnly = settings.isReadOnly();
        this.showMergeCommits = settings.isShowMergeCommits();
        this.localOnly = settings.isLocalOnly();
    }

}
