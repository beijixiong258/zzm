package zzm.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

@Data
public class AccountUser {
    @TableId(type = IdType.ASSIGN_UUID)
    private String id;
    private String name;
    private String email;
    private String role;
    private String username;
    private String invitationHash;
    private Boolean invitationEnabled;
    private String passwordHash;
    private Boolean archived;
    private Boolean mustChangePassword;
    private Boolean demo;
}
